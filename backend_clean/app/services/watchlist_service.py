def clean_optional_abn(clean_abn, value):
    if not value:
        return None
    cleaned = clean_abn(value)
    return cleaned if cleaned else None
