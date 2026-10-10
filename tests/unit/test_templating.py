from pathlib import Path

from revenue_system.skills.templating import TemplateRenderer


def test_pack_template_renders():
    output = TemplateRenderer(Path("packs")).render("brand/templates/first_touch.md.j2", {"company_name": "Example", "contact_name": "Amina", "value_proposition": "Measure campaigns better."})
    assert "Example" in output
    assert "Measure campaigns better." in output

