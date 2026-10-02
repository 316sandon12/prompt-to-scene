using System;
using UnityEngine;
using UnityEngine.Events;

namespace PromptToScene
{
    [DisallowMultipleComponent]
    public sealed class Interaction : MonoBehaviour
    {
        public string template = "door";
        public Transform movingPivot;
        public Vector3 openRotation = new Vector3(0, 90, 0);
        public float interactionRange = 2.5f;
        public bool demoInput = true;
        public UnityEvent onInteracted = new UnityEvent();
        public bool IsOpen { get; private set; }
        public bool Collected { get; private set; }
        public int InteractionCount { get; private set; }
        Quaternion closedRotation;

        void Awake() { closedRotation = movingPivot ? movingPivot.localRotation : Quaternion.identity; }

        // Call from your own controller/input system. Positions are Unity world meters.
        public bool TryInteract(Vector3 worldPosition)
        {
            if (Collected || Vector3.Distance(worldPosition, transform.position) > interactionRange) return false;
            if (template == "pickup") Collected = true;
            else
            {
                if (!movingPivot) return false;
                IsOpen = !IsOpen;
                movingPivot.localRotation = closedRotation * Quaternion.Euler(IsOpen ? openRotation : Vector3.zero);
            }
            InteractionCount++;
            onInteracted.Invoke();
            if (Collected) gameObject.SetActive(false);
            return true;
        }

        void Update()
        {
            if (!demoInput || !Pressed()) return;
            var camera = Camera.main;
            if (!camera) return;
            RaycastHit hit;
            if (Physics.Raycast(camera.transform.position, camera.transform.forward, out hit, interactionRange,
                                ~0, QueryTriggerInteraction.Ignore) && hit.collider.GetComponentInParent<Interaction>() == this)
                TryInteract(camera.transform.position);
        }

        static bool Pressed()
        {
#if ENABLE_LEGACY_INPUT_MANAGER
            return Input.GetKeyDown(KeyCode.E);
#elif ENABLE_INPUT_SYSTEM
            var type = Type.GetType("UnityEngine.InputSystem.Keyboard, Unity.InputSystem");
            var keyboard = type?.GetProperty("current")?.GetValue(null);
            var key = type?.GetProperty("eKey")?.GetValue(keyboard);
            return key != null && (bool)key.GetType().GetProperty("wasPressedThisFrame").GetValue(key);
#else
            return false;
#endif
        }
    }
}
