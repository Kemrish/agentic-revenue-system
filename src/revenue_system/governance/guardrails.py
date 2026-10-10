def wrap_untrusted_content(content: str, source: str) -> str:
    return f"<untrusted_data source={source!r}>\n{content}\n</untrusted_data>"

