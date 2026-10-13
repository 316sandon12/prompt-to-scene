using UnityEngine;
using UnityEngine.UI;

namespace PromptToScene
{
    /// <summary>Fit all inventory slots inside their editable RectTransform at any aspect.</summary>
    [ExecuteAlways, RequireComponent(typeof(GridLayoutGroup))]
    public sealed class ResponsiveItemGrid : MonoBehaviour
    {
        public int preferredColumns = 4;
        void OnEnable() { Fit(); }
        void OnRectTransformDimensionsChange() { Fit(); }
        void OnTransformChildrenChanged() { Fit(); }
        void Fit()
        {
            var grid=GetComponent<GridLayoutGroup>();if(!grid)return;
            var size=((RectTransform)transform).rect.size;
            int columns=Mathf.Max(1,preferredColumns),rows=Mathf.Max(1,Mathf.CeilToInt(transform.childCount/(float)columns));
            grid.constraint=GridLayoutGroup.Constraint.FixedColumnCount;grid.constraintCount=columns;
            grid.cellSize=new Vector2(Mathf.Max(1,(size.x-grid.padding.horizontal-grid.spacing.x*(columns-1))/columns),Mathf.Max(1,(size.y-grid.padding.vertical-grid.spacing.y*(rows-1))/rows));
        }
    }
}
