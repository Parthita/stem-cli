# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0]

### Added
- Initial release of stem CLI tool
- Core node management system with sequential IDs
- Git integration with branch naming convention
- Intent-driven checkpoint creation
- Navigation between nodes with `jump` command
- Global repository registry and view
- AI agent integration through intent declaration
- Filesystem watching with auto-commit functionality
- Cross-platform support (Windows, macOS, Linux)
- Comprehensive error handling and recovery
- Complete test suite with unit and integration tests

### Features
- `stem create` - Initialize stem in Git repository
- `stem branch "prompt"` - Create intent-driven checkpoint
- `stem list` - Display all nodes with summaries
- `stem jump <id>` - Navigate to specific node
- `stem watch` - Monitor filesystem for changes
- `stem global` - View all stem repositories
- `stem doctor` - Diagnose repository issues

### Safety Guarantees
- Non-destructive Git operations
- Atomic state updates with rollback
- Explicit intent requirement (no guessing)
- Git remains source of truth
- Loud failures over silent corruption
