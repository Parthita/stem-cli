stem agent protocol (must follow exactly)

Use stem ONLY when the user's message STARTS WITH "stem ":
- "stem branch : ..."
- "stem update : ..."
- "stem update branch : ..."
- "stem jump ..."

If the user does NOT type a command starting with "stem ", do NOT use stem.

Examples that are NOT stem commands (do NOT use stem):
- "change it to c"
- "make this better"
- "fix the bug"
- "add tests"
- "update the code"

=== CHECK BEFORE PROCEEDING ===
CHECK 1: Does the user message start with "stem "?
- YES -> Continue with stem protocol
- NO -> Stop. Do NOT touch any .stem/ files.

=== FILE EXISTENCE RULE ===
The files `.stem/agent/branch.json` and `.stem/agent/leaf.json` MUST already exist.
- If they exist: Edit them only (never create new ones)
- If they DO NOT exist: Do NOT create them. The system creates them.

=== HUMAN-EDITABLE FIELDS ONLY ===
You may ONLY fill these fields. All other fields are auto-filled by the system:
- branch.json: `prompt`, `summary`
- leaf.json: `old_prompt`, `old_summary`

Do NOT add, modify, or remove any other fields.

=== VALIDATION CHECKLIST ===
Before saving any JSON file:
1. Verify the file already exists (don't create new files)
2. Only edit the human fields listed above
3. Ensure `prompt` is short and clear
4. Ensure `summary` is factual and concise
5. Do NOT combine multiple commands in one JSON

=== COMMAND DETAILS ===

COMMAND: stem branch
Prerequisites:
- `.stem/agent/branch.json` exists
Order:
1. Do the work first.
2. Open `.stem/agent/branch.json` (must already exist).
3. Fill ONLY:
   - `prompt` = short label of what you just built
   - `summary` = short factual summary
4. Save the file.

COMMAND: stem update
Prerequisites:
- `.stem/agent/leaf.json` exists
Order:
1. You just finished OLD work.
2. Open `.stem/agent/leaf.json` (must already exist).
3. Fill ONLY:
   - `old_prompt` = OLD prompt you just finished
   - `old_summary` = summary of OLD work
4. Save the file.
5. Only after saving, start the NEW work.

COMMAND: stem update branch
Prerequisites:
- `.stem/agent/leaf.json` exists
Order:
1. You just finished OLD work.
2. Open `.stem/agent/leaf.json` (must already exist).
3. Fill ONLY:
   - `old_prompt` = OLD prompt you just finished
   - `old_summary` = summary of OLD work
4. Save the file.
5. Do the NEW work.
6. Open `.stem/agent/branch.json`.
7. Fill ONLY:
   - `prompt` = NEW branch prompt (what you built)
   - `summary` = summary of NEW work
8. Save the file.

COMMAND: stem jump
- Do NOT change any JSON files.
- The user runs this command in their terminal.

=== FINAL RULES ===
One JSON = one command. Do not combine commands.
Never create .stem/ files - only edit existing ones.
Never add hidden/system fields.
When in doubt, do NOT use stem.
