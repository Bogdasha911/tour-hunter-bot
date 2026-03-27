from __future__ import annotations

import asyncio
from pathlib import Path


async def run_deploy(repo_dir: Path, remote: str, branch: str) -> tuple[bool, str]:
    commands = [
        ["git", "fetch", remote],
        ["git", "reset", "--hard", f"{remote}/{branch}"],
    ]
    output_parts: list[str] = []
    for cmd in commands:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(repo_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        text = (stdout or b"").decode("utf-8", errors="replace")
        output_parts.append(f"$ {' '.join(cmd)}\n{text}")
        if proc.returncode != 0:
            return False, "\n".join(output_parts)
    return True, "\n".join(output_parts)
