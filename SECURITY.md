# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a security vulnerability and never
include Control D API tokens or other credentials in an issue, pull request, or
workflow log.

Use GitHub's private security advisory feature for this repository when
available. If private advisories are unavailable, contact the repository owner
through GitHub before disclosing the issue publicly.

Include:

- A concise description of the vulnerability.
- The affected file, command, or workflow.
- Reproduction steps that do not contain secrets.
- The potential impact.

## Credential exposure

If a Control D token is exposed:

1. Revoke it immediately in Control D.
2. Create a replacement token.
3. Update the `CONTROLD_API_TOKEN` GitHub repository secret.
4. Remove the token from local files and shell history where possible.
5. Check repository history and workflow logs for additional exposure.

Store tokens in environment variables or GitHub Secrets. Do not commit them to
`config.toml`, `config.local.toml`, issues, or documentation.

## Supported versions

Security fixes target the latest version on the default branch. Pin production
automation to a reviewed commit or release and keep GitHub Actions updated
through Dependabot.
