from .models import PatchProposal


def render_preview(proposal: PatchProposal) -> str:
    summaries = [
        (f"{file.operation.value.upper()} {file.path} (+{file.additions} -{file.deletions})")
        for file in proposal.files
    ]
    return "\n".join(
        [
            "Patch preview",
            *summaries,
            "",
            proposal.raw_diff.rstrip("\n"),
        ]
    )
