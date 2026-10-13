/* Retained Blender geometry. No remote viewer/CDN; named parts are picked from real triangles. */
(() => {
  window.PTSModelViewer = class {
    constructor(canvas, data, onPick) {
      this.canvas=canvas;this.data=data;this.onPick=onPick;this.yaw=.55;this.pitch=.3;this.zoom=1;this.selected="";
      this.abort=new AbortController();const options={signal:this.abort.signal};
      const gl=this.gl=canvas.getContext("webgl",{antialias:true,alpha:true});
      if(!gl)throw Error("浏览器未提供 WebGL；仍可使用引擎预览和部件列表。");
      const shader=(type,source)=>{const s=gl.createShader(type);gl.shaderSource(s,source);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s));return s;};
      const vertex=shader(gl.VERTEX_SHADER,`attribute vec3 position,normal,color;uniform vec3 center;uniform float scale,aspect,zoom,yaw,pitch,selected;varying vec3 tint;
        vec3 turn(vec3 p){p=vec3(p.x,p.z,-p.y);p=vec3(cos(yaw)*p.x+sin(yaw)*p.z,p.y,-sin(yaw)*p.x+cos(yaw)*p.z);return vec3(p.x,cos(pitch)*p.y-sin(pitch)*p.z,sin(pitch)*p.y+cos(pitch)*p.z);}
        void main(){vec3 p=turn((position-center)*scale);vec3 n=normalize(turn(normal));float light=.48+.52*abs(dot(n,normalize(vec3(-.5,.8,1.))));tint=mix(pow(color,vec3(.4545))*light,vec3(.84,.9,.56),selected*.42);gl_Position=vec4(p.x*zoom/aspect,p.y*zoom,-p.z*.15,1.);}`);
      const fragment=shader(gl.FRAGMENT_SHADER,`precision mediump float;varying vec3 tint;void main(){gl_FragColor=vec4(tint,1.);}`);
      this.program=gl.createProgram();gl.attachShader(this.program,vertex);gl.attachShader(this.program,fragment);gl.linkProgram(this.program);gl.deleteShader(vertex);gl.deleteShader(fragment);
      if(!gl.getProgramParameter(this.program,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(this.program));
      const [low,high]=data.bounds;this.center=low.map((v,i)=>(v+high[i])/2);this.scale=1.65/Math.max(.01,Math.hypot(...low.map((v,i)=>high[i]-v)));
      this.parts=data.parts.filter(p=>p.position.length).map(part=>{const buffers={};for(const name of ["position","normal","color"]){buffers[name]=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffers[name]);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(part[name]),gl.STATIC_DRAW);}return {...part,buffers};});
      let down=null;
      canvas.addEventListener("pointerdown",e=>{down={x:e.clientX,y:e.clientY,lastX:e.clientX,lastY:e.clientY,moved:false};canvas.setPointerCapture(e.pointerId);},options);
      canvas.addEventListener("pointermove",e=>{if(!down)return;down.moved ||= Math.hypot(e.clientX-down.x,e.clientY-down.y)>4;if(down.moved){this.yaw+=(e.clientX-down.lastX)*.009;this.pitch=Math.max(-1.4,Math.min(1.4,this.pitch+(e.clientY-down.lastY)*.009));this.draw();}down.lastX=e.clientX;down.lastY=e.clientY;},options);
      canvas.addEventListener("pointerup",e=>{if(down&&!down.moved)this.pick(e.clientX,e.clientY);down=null;},options);
      canvas.addEventListener("pointercancel",()=>{down=null;},options);
      canvas.addEventListener("wheel",e=>{e.preventDefault();this.zoom=Math.max(.35,Math.min(3.5,this.zoom*Math.exp(-e.deltaY*.001)));this.draw();},{...options,passive:false});
      canvas.addEventListener("keydown",e=>{if(["ArrowLeft","ArrowRight","ArrowUp","ArrowDown","+","-","Home"].includes(e.key)){e.preventDefault();if(e.key==="Home"){this.yaw=.55;this.pitch=.3;this.zoom=1;}else if(e.key==="+"||e.key==="-")this.zoom=Math.max(.35,Math.min(3.5,this.zoom*(e.key==="+"?1.1:.9)));else if(e.key==="ArrowLeft"||e.key==="ArrowRight")this.yaw+=e.key==="ArrowLeft"?-.1:.1;else this.pitch=Math.max(-1.4,Math.min(1.4,this.pitch+(e.key==="ArrowUp"?-.1:.1)));this.draw();}},options);
      this.observer=new ResizeObserver(()=>this.draw());this.observer.observe(canvas);this.draw();
    }
    draw(){const gl=this.gl,c=this.canvas,w=c.clientWidth,h=c.clientHeight;if(!w||!h)return;const ratio=Math.min(devicePixelRatio||1,2);c.width=w*ratio;c.height=h*ratio;gl.viewport(0,0,c.width,c.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.useProgram(this.program);
      const u=name=>gl.getUniformLocation(this.program,name);gl.uniform3fv(u("center"),this.center);for(const [key,value]of Object.entries({scale:this.scale,aspect:w/h,zoom:this.zoom,yaw:this.yaw,pitch:this.pitch}))gl.uniform1f(u(key),value);
      for(const p of this.parts){for(const name of ["position","normal","color"]){const a=gl.getAttribLocation(this.program,name);gl.bindBuffer(gl.ARRAY_BUFFER,p.buffers[name]);gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,3,gl.FLOAT,false,0,0);}gl.uniform1f(u("selected"),p.name===this.selected?1:0);gl.drawArrays(gl.TRIANGLES,0,p.position.length/3);}
    }
    project(v){let [x,y,z]=v.map((n,i)=>(n-this.center[i])*this.scale);[y,z]=[z,-y];[x,z]=[Math.cos(this.yaw)*x+Math.sin(this.yaw)*z,-Math.sin(this.yaw)*x+Math.cos(this.yaw)*z];[y,z]=[Math.cos(this.pitch)*y-Math.sin(this.pitch)*z,Math.sin(this.pitch)*y+Math.cos(this.pitch)*z];return [x*this.zoom*this.canvas.clientHeight/this.canvas.clientWidth,y*this.zoom,z];}
    pick(clientX,clientY){const r=this.canvas.getBoundingClientRect(),x=(clientX-r.left)/r.width*2-1,y=1-(clientY-r.top)/r.height*2;let nearest=-Infinity,picked=null;
      for(const p of this.parts)for(let i=0;i<p.position.length;i+=9){const [a,b,c]=[0,3,6].map(k=>this.project(p.position.slice(i+k,i+k+3)));const det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);if(Math.abs(det)<1e-10)continue;const u=((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/det,v=((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/det;if(u<0||v<0||u+v>1)continue;const z=u*a[2]+v*b[2]+(1-u-v)*c[2];if(z>nearest){nearest=z;picked=p.name;}}
      if(picked){this.selected=picked;this.draw();this.onPick(picked);}
    }
    dispose(){this.abort.abort();this.observer.disconnect();for(const p of this.parts)for(const b of Object.values(p.buffers))this.gl.deleteBuffer(b);this.gl.deleteProgram(this.program);}
  };
  window.PTSImageSelection=class {
    constructor(canvas,url,onSelect){this.canvas=canvas;this.context=canvas.getContext("2d");this.rect=null;this.abort=new AbortController();this.image=new Image();this.image.onload=()=>this.draw();this.image.src=url;this.observer=new ResizeObserver(()=>this.draw());this.observer.observe(canvas);let start=null;const opts={signal:this.abort.signal};const point=e=>{const r=canvas.getBoundingClientRect(),b=this.box;return [Math.max(0,Math.min(1,(e.clientX-r.left-b.x)/b.w)),Math.max(0,Math.min(1,(e.clientY-r.top-b.y)/b.h))];};canvas.addEventListener("pointerdown",e=>{if(!this.box)return;start=point(e);canvas.setPointerCapture(e.pointerId);},opts);canvas.addEventListener("pointermove",e=>{if(!start)return;const p=point(e);this.rect=[Math.min(start[0],p[0]),Math.min(start[1],p[1]),Math.abs(p[0]-start[0]),Math.abs(p[1]-start[1])];this.draw();},opts);const end=()=>{if(start&&this.rect&&this.rect[2]*this.image.naturalWidth>=1&&this.rect[3]*this.image.naturalHeight>=1)onSelect(this.rect);start=null;};canvas.addEventListener("pointerup",end,opts);canvas.addEventListener("pointercancel",()=>{start=null;},opts);}
    select(rect){this.rect=rect;this.draw();}
    draw(){const c=this.canvas,ctx=this.context,img=this.image;if(!img.naturalWidth)return;const w=c.clientWidth,h=c.clientHeight;if(!w||!h)return;const d=Math.min(devicePixelRatio||1,2);c.width=w*d;c.height=h*d;ctx.scale(d,d);const scale=Math.min((w-32)/img.naturalWidth,(h-32)/img.naturalHeight);const b=this.box={w:img.naturalWidth*scale,h:img.naturalHeight*scale};b.x=(w-b.w)/2;b.y=(h-b.h)/2;ctx.drawImage(img,b.x,b.y,b.w,b.h);if(this.rect){const [x,y,rw,rh]=this.rect,px=b.x+x*b.w,py=b.y+y*b.h,pw=rw*b.w,ph=rh*b.h;ctx.fillStyle="rgba(9,13,15,.62)";ctx.beginPath();ctx.rect(b.x,b.y,b.w,b.h);ctx.rect(px,py,pw,ph);ctx.fill("evenodd");ctx.strokeStyle="#d4e58b";ctx.lineWidth=2;ctx.strokeRect(px,py,pw,ph);}}
    dispose(){this.abort.abort();this.observer.disconnect();this.image.onload=null;}
  };
})();
