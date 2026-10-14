using UnityEngine;

namespace PromptToScene
{
    [RequireComponent(typeof(Interaction))]
    public sealed class GameplayTrigger : MonoBehaviour
    {
        public string flowId, ruleId;
        GameSession session;
        void Start() { session = GameSession.Find(flowId); if (session) { session.Restored += RestoreState; RestoreState(); } }
        void OnDestroy() { if (session) session.Restored -= RestoreState; }
        public bool TryApply()
        {
            if (!session) session = GameSession.Find(flowId);
            return session && session.TryRule(ruleId);
        }
        void RestoreState()
        {
            var rule = session.Rule(ruleId);
            if (rule != null && rule.once && session.IsComplete(ruleId)) GetComponent<Interaction>().RestoreCompleted();
        }
    }
}
