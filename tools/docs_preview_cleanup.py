"""Delete the Cloudflare Pages deployments of a documentation preview branch."""

from __future__ import annotations

from typing import Annotated

from cloudflare import Cloudflare
from cyclopts import App, Parameter

app = App(name="docs-preview-cleanup", help=__doc__)


@app.default
def cleanup(
    branch: str,
    *,
    account_id: Annotated[str, Parameter(env_var="CLOUDFLARE_ACCOUNT_ID")],
    api_token: Annotated[str, Parameter(env_var="CLOUDFLARE_API_TOKEN")],
    project: str = "strawchemy",
) -> None:
    """Delete every preview deployment built from the given branch."""
    deployments = Cloudflare(api_token=api_token).pages.projects.deployments
    # Fully listed before deleting: deletions would shift the pages still being fetched.
    ids = [
        deployment.id
        for deployment in deployments.list(project, account_id=account_id, env="preview")
        if deployment.deployment_trigger.metadata.branch == branch
    ]
    print(f"Found {len(ids)} deployment(s) for {branch}")
    for deployment_id in ids:
        # force also deletes the deployment the branch alias points to
        deployments.delete(deployment_id, account_id=account_id, project_name=project, force=True)
        print(f"Deleted {deployment_id}")


if __name__ == "__main__":
    app()
