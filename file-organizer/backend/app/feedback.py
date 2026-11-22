from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .classifier import ClassificationProposal
from .models import Classification, Feedback, File


def record_feedback(
    db: Session,
    file: File,
    classification: Classification | None,
    decision: str,
) -> Feedback | None:
    if classification is None or decision not in {"approved", "rejected"}:
        return None
    feedback = Feedback(
        user_id=file.user_id,
        file_id=file.id,
        decision=decision,
        document_type=classification.document_type,
        category=classification.category,
        subcategory=classification.subcategory,
        tags_json=classification.tags_json,
        path_json=classification.suggested_path_json,
        confidence=classification.confidence,
    )
    db.add(feedback)
    db.flush()
    return feedback


def recent_feedback(db: Session, user_id: str, limit: int = 12) -> list[Feedback]:
    return list(
        db.scalars(
            select(Feedback)
            .where(Feedback.user_id == user_id)
            .order_by(Feedback.created_at.desc())
            .limit(limit)
        ).all()
    )


def feedback_examples(db: Session, user_id: str, limit: int = 12) -> list[dict]:
    examples: list[dict] = []
    for feedback in recent_feedback(db, user_id, limit):
        examples.append(
            {
                "decision": feedback.decision,
                "documentType": feedback.document_type,
                "category": feedback.category,
                "subcategory": feedback.subcategory,
                "path": json.loads(feedback.path_json or "[]"),
                "tags": json.loads(feedback.tags_json or "[]"),
            }
        )
    return examples


def learned_destination(db: Session, user_id: str, document_type: str) -> dict | None:
    """Most frequent user-approved path for this document type."""
    if not document_type or document_type == "other":
        return None
    rows = db.execute(
        select(Feedback.path_json, func.count(Feedback.id).label("uses"))
        .where(
            Feedback.user_id == user_id,
            Feedback.decision == "approved",
            Feedback.document_type == document_type,
        )
        .group_by(Feedback.path_json)
        .order_by(func.count(Feedback.id).desc())
        .limit(3)
    ).all()
    for path_json, _uses in rows:
        path = json.loads(path_json or "[]")
        if not path:
            continue
        latest = db.scalar(
            select(Feedback)
            .where(
                Feedback.user_id == user_id,
                Feedback.decision == "approved",
                Feedback.document_type == document_type,
                Feedback.path_json == path_json,
            )
            .order_by(Feedback.created_at.desc())
            .limit(1)
        )
        return {
            "path": path,
            "category": latest.category if latest else path[0],
            "subcategory": latest.subcategory if latest else (path[1] if len(path) > 1 else None),
            "tags": json.loads(latest.tags_json or "[]") if latest else [],
        }
    return None


def apply_learning(
    db: Session,
    user_id: str,
    proposal: ClassificationProposal,
    threshold: float,
) -> ClassificationProposal:
    """Reuse a user's approved destination for the same document type.

    The model still classifies the file; this only replaces the proposed destination
    when the user has already confirmed one for that document type. Confidence is
    raised to just above the user's auto-organize threshold so repeated, previously
    approved types can be organized automatically.
    """
    if proposal.document_type == "other":
        return proposal.model_copy(update={"requires_review": True})

    learned = learned_destination(db, user_id, proposal.document_type)
    if learned:
        confidence = max(proposal.confidence, min(0.95, threshold + 0.05))
        rationale = (
            proposal.rationale
            + " Reused your previous approved folder for this document type."
        )[:500]
        proposal = proposal.model_copy(
            update={
                "suggested_path": learned["path"],
                "category": learned["category"] or proposal.category,
                "subcategory": learned["subcategory"],
                "tags": learned["tags"] or proposal.tags,
                "confidence": confidence,
                "rationale": rationale,
            }
        )
    return proposal.normalized()
