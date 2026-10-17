"""One consistent, actionable pre-call limit check for single and batch generation."""

from app.services.content import ContentError


def require_source_input(source, limit):
    count = len(source.content)
    label = source.title[:70]
    if not source.content.strip():
        raise ContentError(422, f'资料「{label}」（{source.id}）正文为空，不能生成；当前 {count} 字符，上限 {limit}。')
    if count > limit:
        raise ContentError(422, f'资料「{label}」（{source.id}）正文 {count} 字符，超过当前输入上限 {limit}；'
                               '请缩小资料范围或在配置中调整 MEMORY_OS_AI_MAX_INPUT_CHARS 后重启。')
