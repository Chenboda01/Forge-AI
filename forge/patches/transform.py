from .models import FilePatch, PatchApplicationError, PatchOperation


def apply_file_patch(file_patch: FilePatch, original: str) -> str:
    original_lines = original.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in original else "\n"
    output: list[str] = []
    cursor = 0
    for hunk in file_patch.hunks:
        start = hunk.old_start if hunk.old_count == 0 else max(hunk.old_start - 1, 0)
        output.extend(original_lines[cursor:start])
        cursor = start
        previous_prefix = ""
        for line in hunk.lines:
            if line == "\\ No newline at end of file":
                if previous_prefix in {" ", "+"} and output:
                    output[-1] = output[-1].removesuffix("\n").removesuffix("\r")
                continue
            previous_prefix = line[0]
            if previous_prefix == " ":
                output.append(original_lines[cursor])
                cursor += 1
            elif previous_prefix == "-":
                cursor += 1
            elif previous_prefix == "+":
                output.append(f"{line[1:]}{newline}")
        output.extend(original_lines[cursor : start + hunk.old_count])
        cursor = start + hunk.old_count
    output.extend(original_lines[cursor:])
    content = "".join(output)
    if file_patch.operation is PatchOperation.DELETE and content:
        raise PatchApplicationError(f"Delete patch does not remove all content: {file_patch.path}")
    return content
