"""Render the proposal Markdown as editable LaTeX; optionally build its PDF.

Uses Python's standard library and an existing XeLaTeX installation. The small
Markdown subset is intentional: headings, paragraphs, flat lists, links, bold,
tables, explicit <br> breaks, inline code, {{personal-detail placeholders}},
and pagebreak comments. Level-four headings are standalone unnumbered labels.
Bibliography metadata comes from docs/references.bib.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PDF_BASENAME = "EviRecall_Project_Proposal"
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
    "locomo": "locomo2024",
}


def escape(value: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%",
        "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
        "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def inline(value: str) -> str:
    if "<br>" in value:
        return r"\newline{}".join(inline(part.strip()) for part in value.split("<br>"))
    pattern = re.compile(r"\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)|\{\{([^{}]+)\}\}")
    parts, start = [], 0
    for match in pattern.finditer(value):
        parts.append(escape(value[start:match.start()]))
        if match.group(1) is not None:
            parts.append(r"\textbf{" + inline(match.group(1)) + "}")
        elif match.group(2) is not None:
            parts.append(r"{\small\texttt{" + escape(match.group(2)) + "}}")
        elif match.group(5) is not None:
            parts.append(r"\personal{" + escape(match.group(5)) + "}")
        else:
            label, target = match.group(3, 4)
            if target.startswith("references.md#"):
                key = CITATIONS[target.split("#", 1)[1]]
                parts.append(r"\cite{" + key + "}")
            elif target.startswith(("https://", "mailto:")):
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
    lines = [r"\clearpage", r"\begin{thebibliography}{99}",
             r"\fontsize{10}{12.5}\selectfont", r"\setlength{\itemsep}{7pt}"]
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
        label = "Paper" if "eprint" in fields or "booktitle" in fields else "Source"
        if "github.com" in fields["url"]:
            label = "Code"
        elif "docs.langchain.com" in fields["url"]:
            label = "Docs"
        links = [r"\href{" + fields["url"] + "}{[" + label + "]}"]
        for field, link_label in (("repository", "Code"), ("dataset", "Data")):
            if field in fields and fields[field] != fields["url"]:
                links.append(r"\href{" + fields[field] + "}{[" + link_label + "]}")
        lines.append(r"\bibitem{" + key + "}" + escape(description) + " " + " ".join(links))
    lines.append(r"\end{thebibliography}")
    return "\n".join(lines)


def render_table(rows: list[str]) -> str:
    cells = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in rows]
    header, separator, *body = cells
    is_team_table = header == ["Member", "Name", "Student ID", "University email"]
    count = len(header)
    if not all(re.fullmatch(r":?-+:?", cell) for cell in separator):
        raise ValueError("Invalid Markdown table separator")
    if any(len(row) != count for row in cells):
        raise ValueError("Inconsistent Markdown table columns")
    widths = {2: [0.25, 0.75], 3: [0.22, 0.49, 0.29], 4: [0.12, 0.25, 0.25, 0.38]}[count]
    columns = "".join(r">{\raggedright\arraybackslash}p{\dimexpr " + str(width)
                      + r"\linewidth-2\tabcolsep\relax}" for width in widths)
    head = " & ".join(r"\textcolor{accent}{\textbf{" + inline(cell) + "}}" for cell in header) + r" \\"
    output = [r"\par\begingroup", r"\fontsize{10}{12.2}\selectfont",
              r"\setlength{\tabcolsep}{6pt}", r"\renewcommand{\arraystretch}{1.18}",
              r"\setlength{\LTpre}{5pt}", r"\setlength{\LTpost}{7pt}",
              r"\begin{longtable}{" + columns + "}", r"\hline\noalign{\vskip 5pt}", head,
              r"\noalign{\vskip 4pt}\hline\noalign{\vskip 5pt}", r"\endfirsthead",
              r"\hline\noalign{\vskip 5pt}", head,
              r"\noalign{\vskip 4pt}\hline\noalign{\vskip 5pt}", r"\endhead",
              r"\hline", r"\endfoot"]
    for row in body:
        rendered = [inline(cell) for cell in row]
        if is_team_table:
            rendered = [cell if index == 0 else r"\textcolor{linkblue}{" + cell + "}"
                        for index, cell in enumerate(rendered)]
        output.append(" & ".join(rendered) + r" \\")
        # A noalign gap remains visible even when a cell wraps to several lines.
        output.append(r"\noalign{\vskip 7pt}")
    output += [r"\end{longtable}", r"\endgroup\par"]
    return "\n".join(output)


def render_body() -> str:
    output, paragraph = [], []
    list_open = False

    def flush():
        if paragraph:
            text = " ".join(paragraph)
            rendered = inline(text)
            output.append(rendered + r"\par" + "\n")
            paragraph.clear()

    source_lines = (DOCS / "proposal.md").read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(source_lines):
        line = source_lines[index]
        index += 1
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
        if line.startswith("|"):
            flush()
            rows = [line]
            while index < len(source_lines) and source_lines[index].startswith("|"):
                rows.append(source_lines[index])
                index += 1
            output.append(render_table(rows))
        elif line == "<!-- pagebreak -->":
            flush()
            output.append(r"\clearpage")
        elif not line.strip():
            flush()
        elif line.startswith("#### "):
            flush()
            output.append(r"\subsubsection*{" + inline(line[5:]) + "}")
        elif line.startswith("### "):
            flush()
            title = re.sub(r"^\d+\.\d+\s*", "", line[4:])
            output.append(r"\subsection{" + escape(title) + "}")
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
\documentclass[a4paper,11pt]{article}
\usepackage[margin=21mm,top=21mm,bottom=21mm,headheight=14pt]{geometry}
\usepackage{xcolor}
\definecolor{accent}{HTML}{203B59}
\definecolor{linkblue}{HTML}{145BC4}
\definecolor{tablehead}{HTML}{EDF3FA}
\usepackage[colorlinks=true,linkcolor=linkblue,urlcolor=linkblue,citecolor=linkblue]{hyperref}
\newcommand{\personal}[1]{\textcolor{linkblue}{\textbf{[#1]}}}
\usepackage{array,longtable}
\setlength{\LTleft}{0pt}
\setlength{\LTright}{0pt}
\usepackage{enumitem}
\setlist[itemize]{leftmargin=1.5em,topsep=5pt,itemsep=5pt,parsep=0pt}
\usepackage{titlesec}
\titleformat{\section}{\large\bfseries\color{accent}}{\thesection}{0.6em}{}
\titleformat{\subsection}{\normalsize\bfseries}{\thesubsection}{0.6em}{}
\titleformat{\subsubsection}[block]{\normalsize\bfseries}{}{0pt}{}
\titlespacing*{\section}{0pt}{13pt}{7pt}
\titlespacing*{\subsection}{0pt}{10pt}{5pt}
\titlespacing*{\subsubsection}{0pt}{9pt}{4pt}
\setlength{\parindent}{0pt}
\setlength{\parskip}{7pt}
\linespread{1.08}
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\color{accent}EviRecall}
\fancyhead[R]{\small\color{accent}Project Proposal}
\fancyfoot[C]{\small\thepage}
\renewcommand{\headrulewidth}{0.3pt}
\fancypagestyle{plain}{\fancyhf{}\fancyfoot[C]{\small\thepage}\renewcommand{\headrulewidth}{0pt}}
\clubpenalty=10000
\widowpenalty=10000
\emergencystretch=3em
\sloppy
\hypersetup{pdftitle={EviRecall - Project Proposal},pdfauthor={EviRecall Team},pdfsubject={Natural Language Processing (CSC5051 / CSC6052 / MDS5110), Fall 2026}}
\begin{document}
\thispagestyle{plain}
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
                    f"-output-directory={output_dir}", f"-jobname={PDF_BASENAME}", str(tex_path)]
        for _ in range(2):
            result = subprocess.run(command, cwd=DOCS, capture_output=True, encoding="utf-8", errors="replace")
            if result.returncode:
                print(result.stdout[-6000:])
                print(result.stderr[-2000:])
                raise SystemExit(result.returncode)
        print(f"Built {(output_dir / (PDF_BASENAME + '.pdf')).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
