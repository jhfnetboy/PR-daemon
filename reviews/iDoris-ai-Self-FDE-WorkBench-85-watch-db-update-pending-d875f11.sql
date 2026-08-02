-- Active DB `.state/pr-daemon/pr-watch.sqlite` was locked by PID 79775 during review finalization.
-- Mirror DB `reviews/pr-watch.sqlite` was updated successfully.
UPDATE pr_watch_targets
SET head_oid='d875f114098bfc1d71af88c9f0d21dbedbf21729',
    last_reviewed_head_oid='d875f114098bfc1d71af88c9f0d21dbedbf21729',
    status='changes_requested',
    last_reviewed_at=CURRENT_TIMESTAMP,
    review_decision='REQUEST_CHANGES',
    last_review_event='REQUEST_CHANGES'
WHERE repo='iDoris-ai/Self-FDE-WorkBench'
  AND pr_number=85;
