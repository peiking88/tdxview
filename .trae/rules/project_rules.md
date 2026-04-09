# Project Rules for tdxview

## Git Configuration
- **GitHub Domain**: Use `bgithub.xyz` domain for accessing GitHub repositories
- **SSL Verification**: Disable SSL certificate verification for pushes
- **Username**: `peiking88`
- **Credentials**: Use environment variable `GITHUB_TOKEN` for authentication
- **No Sensitive Information**: Ensure no sensitive information is committed to the repository

## Language Rules
- **Working Process**: Use Chinese for output during work process
- **Commit Messages**: Use English for commit messages
- **README**: Use English for README files

## Build Rules
- **Parallel Compilation**: Use `-j$(nproc)` parameter for ninja or make builds
- **Third-party Code**: Do NOT modify source files in `3rdparty` and `external` directories

## Logging
- **Log Directory**: Save all logs to `log` directory

## Debugging Rules
- **No Simplification**: Do NOT simplify or bypass problems during debugging
- **Test Requirements**: All unit tests must pass before executing new tasks

## Implementation Notes
1. Always check for existing lint and typecheck commands before making changes
2. Run appropriate validation commands after code changes
3. Follow existing code conventions and patterns
4. Use existing libraries and utilities when available