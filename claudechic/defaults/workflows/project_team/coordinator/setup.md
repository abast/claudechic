# Setup Phase

1. Determine $WORKFLOW_ROOT (must be absolute path)
2. Check for existing state at `$STATE_DIR/STATUS.md`
   - If exists: ask user to resume or start fresh
3. Derive project_name from vision (short, lowercase, underscores)
4. Create state directory at $STATE_DIR with STATUS.md and userprompt.md
5. Check for git -- advise user if no version control detected
