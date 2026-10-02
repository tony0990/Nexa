from typing import List
from intelligence.schemas import ActionCandidate, DuplicateDecision

class MergeAdvisor:
    """
    Provides merge recommendations based on DuplicateService decisions.
    Purely advisory — never executes the merge (§9.2).
    """

    def recommend(self, decisions: List[DuplicateDecision]) -> List[str]:
        """
        Returns a list of recommended actions for the UI.
        """
        recommendations = []
        for d in decisions:
            if d.recommended_action == "merge":
                recommendations.append(f"Merge {d.compared_ids[0]} into {d.compared_ids[1]}")
            elif d.recommended_action == "flag_for_review":
                recommendations.append(f"Review potential duplicate: {d.compared_ids[0]} & {d.compared_ids[1]}")

        return recommendations
