-- Apply after watcher releases lock:
UPDATE pr_watch_targets SET last_reviewed_head_oid='5db90d1da5aa2a2d074bc1fc32ba880707edda77', status='approved', last_reviewed_at=CURRENT_TIMESTAMP, review_decision='APPROVE' WHERE repo='iDoris-ai/auraai-packages' AND pr_number=34;
