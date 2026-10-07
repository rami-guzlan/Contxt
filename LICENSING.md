# Licensing

This repository is private and not yet licensed for use by others.

The intended structure for the public release, from the product specification (section 19):

- **Code license: AGPL-3.0.** People may run and modify the product; modified versions offered
  as a hosted service must remain available under the same terms.
- **Contributor agreement.** Contributors grant the project the rights it needs to keep future
  licensing options open. Until it exists, outside contributions are not accepted.
- **Trademark policy.** Forks may use the code but not imply they are the official product.
- **Extension contract.** Connectors and templates use documented interfaces, so community
  contributions do not fork the core.

Before the first public release:

1. Qualified counsel reviews the license choice, the contributor agreement and the trademark
   policy against the final legal entity and contribution model.
2. `LICENSE` is added with the full, unmodified license text, and each package's
   `pyproject.toml` and `package.json` declares the license.
3. Third-party notices are generated from the locked dependencies (`uv.lock`,
   `package-lock.json`) and checked for compatibility.
4. The public repository starts from a fresh history (this repository has one): no private
   content or real Brain is ever part of it. The demo Brains in `brains/` are invented.
