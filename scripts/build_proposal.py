"""Render the proposal Markdown as editable LaTeX; optionally build its PDF.

Uses Python's standard library and an existing XeLaTeX installation. The small
Markdown subset is intentional: headings, paragraphs, flat lists, links, bold,
and inline code. Bibliography metadata comes from docs/references.bib.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CITATIONS = {
    "smurfs": "smurfs2025",
    "tiermem": "tiermem2026",
    "jev": "jev2026",
    "longmemeval": "longmemeval2025",
    "memoryarena": "memoryarena2026",
    "mast": "mast2025",
    "governed": "governed2026",
    "deepagents": "deepagents2026",
    "memoryagentbench": "memoryagentbench2026",
    "stale": "stale2026",
    "magentic": "magentic2024",
    "twinmarket": "twinmarket2025",
    "easymed": "easymed2025",
    "amem": "amem2025",
    "mem0": "mem02025",
    "course": "course2026",
}


def escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%",
        "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
        "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def inline(value: str) -> str:
    pattern = re.compile(r"\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)")
    parts, start = [], 0
    for match in pattern.finditer(value):
        parts.append(escape(value[start:match.start()]))
        if match.group(1) is not None:
            parts.append(r"\textbf{" + inline(match.group(1)) + "}")
        elif match.group(2) is not None:
            parts.append(r"{\small\texttt{" + escape(match.group(2)) + "}}")
        else:
            label, target = match.group(3, 4)
            if target.startswith("references.md#"):
                key = CITATIONS[target.split("#", 1)[1]]
                parts.append(r"\cite{" + key + "}")
            elif target.startswith("https://"):
                parts.append(r"\href{" + target.replace("%", r"\%") + "}{" + escape(label) + "}")
            else:
                parts.append(escape(label))
        start = match.end()
    parts.append(escape(value[start:]))
    return "".join(parts)


def read_bib() -> dict[str, dict[str, str]]:
    text = (DOCS / "references.bib").read_text(encoding="utf-8")
    records = {}
    for record in re.split(r"(?=@\w+\{)", text):
        if not record.strip():
            continue
        header = re.match(r"@\w+\{([^,]+),", record)
        if header is None:
            raise ValueError("Unsupported BibTeX record")
        fields, pos = {}, header.end()
        while field := re.search(r"(\w+)\s*=\s*\{", record[pos:]):
            name = field.group(1)
            begin = pos + field.end()
            end, depth = begin, 1
            while depth and end < len(record):
                depth += (record[end] == "{") - (record[end] == "}")
                end += 1
            if depth:
                raise ValueError(f"Unbalanced BibTeX field: {name}")
            raw_value = record[begin:end - 1]
            if name == "author" and raw_value.startswith("{"):
                fields["corporate_author"] = "true"
            fields[name] = raw_value.replace("{", "").replace("}", "")
            pos = end
        records[header.group(1)] = fields
    return records


def bibliography() -> str:
    entries = read_bib()
    lines = [r"\begin{thebibliography}{99}", r"\small"]
    for key in CITATIONS.values():
        fields = entries[key]
        authors = fields["author"].split(" and ")
        if not fields.get("corporate_author"):
            authors = [" ".join(reversed(a.split(", "))) if ", " in a else a for a in authors]
        author = ", ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
        description = f'{author}. {fields["title"]}. {fields["year"]}.'
        if "eprint" in fields:
            description += " arXiv:" + fields["eprint"] + "."
        elif "booktitle" in fields:
            description += " NAACL, pp. " + fields["pages"].replace("--", "-") + "."
        else:
            description += " " + fields.get("howpublished", "Documentation") + "; accessed 2026-10-27."
        lines.append(r"\bibitem{" + key + "}" + escape(description)
                     + r" \href{" + fields["url"] + r"}{[source]}")
    lines.append(r"\end{thebibliography}")
    return "\n".join(lines)


def render_body() -> str:
    output, paragraph = [], []
    list_open = False

    def flush():
        if paragraph:
            text = " ".join(paragraph)
            rendered = inline(text)
            if text.startswith("**Member "):
                rendered = r"\begin{samepage}" + rendered + r"\par\end{samepage}"
            output.append(rendered + "\n")
            paragraph.clear()

    for line in (DOCS / "proposal.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            continue
        if line.startswith("- "):
            flush()
            if not list_open:
                output.append(r"\begin{itemize}")
                list_open = True
            output.append(r"\item " + inline(line[2:]))
            continue
        if list_open:
            output.append(r"\end{itemize}")
            list_open = False
        if not line.strip():
            flush()
        elif line.startswith("## "):
            flush()
            title = re.sub(r"^\d+\.\s*", "", line[3:])
            output.append(r"\section{" + escape(title) + "}")
        else:
            paragraph.append(line)
    flush()
    if list_open:
        output.append(r"\end{itemize}")
    return "\n".join(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", action="store_true", help="Compile with XeLaTeX (no package auto-install)")
    args = parser.parse_args()
    preamble = r"""% Generated from docs/proposal.md and docs/references.bib.
% Edit those sources, then run python scripts/build_proposal.py.
\documentclass[a4paper,10pt]{article}
\usepackage[margin=21mm,top=18mm,bottom=20mm]{geometry}
\usepackage{xcolor}
\definecolor{accent}{HTML}{204B63}
\usepackage[colorlinks=true,linkcolor=accent,urlcolor=accent,citecolor=accent]{hyperref}
\usepackage{enumitem}
\setlist[itemize]{leftmargin=1.5em,topsep=3pt,itemsep=2pt,parsep=0pt}
\usepackage{titlesec}
\titleformat{\section}{\large\bfseries}{\thesection}{0.6em}{}
\titlespacing*{\section}{0pt}{10pt}{4pt}
\setlength{\parindent}{0pt}
\setlength{\parskip}{4pt}
\linespread{1.05}
\pagestyle{plain}
\clubpenalty=10000
\widowpenalty=10000
\emergencystretch=3em
\sloppy
\hypersetup{pdftitle={EviRecall Proposal v0.2},pdfauthor={EviRecall Team}}
\begin{document}
{\color{accent}\LARGE\bfseries EviRecall}\par
{\large\bfseries Evidence-Aware Memory for Long-Horizon Multi-Agent Tasks}\par
\vspace{4pt}\hrule\vspace{7pt}
"""
    source = preamble + render_body() + "\n" + bibliography() + "\n\\end{document}\n"
    tex_path = DOCS / "proposal.tex"
    tex_path.write_text(source, encoding="utf-8")
    print(f"Generated {tex_path.relative_to(ROOT)}")
    if args.pdf:
        executable = shutil.which("xelatex")
        if executable is None:
            raise SystemExit("XeLaTeX not found; editable LaTeX source has been generated.")
        output_dir = ROOT / "output" / "pdf"
        output_dir.mkdir(parents=True, exist_ok=True)
        command = [executable]
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, check=True)
        if "miktex" in version.stdout.lower():
            command.append("--disable-installer")
        command += ["-interaction=nonstopmode", "-halt-on-error",
                    f"-output-directory={output_dir}", "-jobname=evirecall-proposal-v0.2", str(tex_path)]
        for _ in range(2):
            result = subprocess.run(command, cwd=DOCS, capture_output=True, encoding="utf-8", errors="replace")
            if result.returncode:
                print(result.stdout[-6000:])
                print(result.stderr[-2000:])
                raise SystemExit(result.returncode)
        print(f"Built {(output_dir / 'evirecall-proposal-v0.2.pdf').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
