"""Build one self-contained offline HTML questionnaire. No third-party dependencies."""

from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build() -> Path:
    data = json.loads((ROOT / "scripts/questionnaire_data.json").read_text(encoding="utf-8"))
    template = (ROOT / "scripts/questionnaire.template.html").read_text(encoding="utf-8")
    navigation, panels = [], []
    question_number = 0
    for index, section in enumerate(data["sections"]):
        sid = escape(section["id"], quote=True)
        navigation.append(f'<button type="button" data-step="{sid}"><span class="step-number">{index + 1:02}</span>'
                          f'{escape(section["title"])}<span id="count-{sid}" class="step-count">0/{len(section["questions"])}</span></button>')
        panels.append(f'<section class="panel" id="panel-{sid}" aria-labelledby="title-{sid}"' + (' hidden' if index else '') + '>')
        panels.append(f'<p class="section-kicker">{index + 1:02} / DISCUSSION</p><h2 id="title-{sid}" tabindex="-1">{escape(section["title"])}</h2>'
                      f'<p class="section-subtitle">{escape(section["subtitle"])}</p><p class="owner">{escape(section["owner"])}</p>')
        if section.get("scenario"):
            panels.append(f'<div class="scenario">{escape(section["scenario"])}</div>')
        for question in section["questions"]:
            question_number += 1
            qid = escape(question["id"], quote=True)
            panels.append(f'<fieldset class="question" aria-describedby="context-{qid}"><legend><span class="question-number">{question_number:02}</span>{escape(question["title"])}</legend>'
                          f'<p id="context-{qid}" class="context">{escape(question["context"])}</p><p class="recommendation"><strong>建议起点：</strong>{escape(question["recommendation"])}</p><div class="options">')
            for option in question["options"]:
                badge = '<span class="badge">建议</span>' if option.get("recommended") else ''
                panels.append(f'<label class="option"><input type="radio" name="q-{qid}" value="{escape(option["id"], quote=True)}">'
                              f'<span class="option-copy"><span class="option-title">{escape(option["title"])}{badge}</span>'
                              f'<span class="option-detail">{escape(option["detail"])}</span></span></label>')
            panels.append(f'<label class="option option-other"><input type="radio" name="q-{qid}" value="other"><span class="option-copy"><span class="option-title">其他方案／需要讨论（请补充具体想法）</span></span></label></div>'
                          f'<details class="notes" id="notes-{qid}"><summary>补充理由、顾虑或自己的方案</summary><label for="note-{qid}">关于「{escape(question["title"])}」的补充</label>'
                          f'<textarea id="note-{qid}" maxlength="5000" placeholder="可以写同意的前提、需要验证的问题，或你更倾向的方案。"></textarea></details></fieldset>')
        panels.append('<div class="field-grid">')
        for field in section["fields"]:
            fid, kind = escape(field["id"], quote=True), field["type"]
            wide = ' wide' if kind == 'textarea' or field["id"] in ('provider', 'meeting_time', 'editor', 'reviewers') else ''
            panels.append(f'<label class="field{wide}" for="field-{fid}">{escape(field["label"])}')
            placeholder = escape(field.get("placeholder", ""), quote=True)
            if kind == 'textarea':
                panels.append(f'<textarea id="field-{fid}" maxlength="5000" placeholder="{placeholder}"></textarea>')
            elif kind == 'select':
                panels.append(f'<select id="field-{fid}"><option value="">待选择</option>' + ''.join(f'<option value="{escape(o, quote=True)}">{escape(o)}</option>' for o in field["options"]) + '</select>')
            else:
                attributes = ''.join(f' {a}="{escape(str(field[a]), quote=True)}"' for a in ('min', 'max') if a in field)
                if kind == 'number':
                    attributes += ' step="any"'
                panels.append(f'<input id="field-{fid}" type="{kind}" placeholder="{placeholder}" maxlength="5000"{attributes}>')
            panels.append('</label>')
        panels.append('</div><div class="section-actions">')
        if index:
            panels.append(f'<button type="button" data-step="{data["sections"][index - 1]["id"]}">上一个主题</button>')
        next_id = data["sections"][index + 1]["id"] if index + 1 < len(data["sections"]) else 'summary'
        next_label = '下一个主题' if next_id != 'summary' else '查看汇总与导出'
        panels.append(f'<button type="button" class="primary next" data-step="{next_id}">{next_label} →</button></div>'
                      '<p class="helper">选项不预选；补充信息可暂留空。“其他方案”填写理由后计入进度。</p></section>')
    members = ''.join(f'<option value="{m["id"]}">{escape(m["name"])} · {escape(m["role"])}</option>' for m in data["members"])
    embedded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = template.replace('__MEMBER_OPTIONS__', members).replace('__NAVIGATION__', '\n'.join(navigation)).replace('__FORM__', '\n'.join(panels)).replace('__SURVEY_DATA__', embedded)
    output = ROOT / 'docs/discussion.html'
    output.write_text(html, encoding='utf-8')
    return output


if __name__ == '__main__':
    print(build())
