from pipeline.quality_gate.policy import Policy, Severity


class TitleDescriptionCtaCheck:
    def __init__(self, metadata: dict = None, policy: Policy | None = None):
        self.metadata = metadata or {}
        self.policy = policy or Policy.from_env()

    def run(self) -> list[dict]:
        results = []
        title = self.metadata.get("title") or self.metadata.get("titulo") or ""
        desc = self.metadata.get("description") or self.metadata.get("descricao") or ""
        cta = self.metadata.get("cta") or ""
        # Regras determinísticas apenas
        if not title or not str(title).strip():
            results.append({"name": "title_present", "status": "FAIL", "severity": Severity.CRITICAL, "message": "Title is empty."})
        else:
            results.append({"name": "title_present", "status": "PASS", "severity": Severity.CRITICAL, "message": f"Title present ({len(str(title))} chars)."})
        if desc and not str(desc).strip():
            results.append({"name": "description_empty", "status": "WARNING", "severity": Severity.WARNING, "message": "Description is empty."})
        else:
            results.append({"name": "description_present", "status": "PASS", "severity": Severity.WARNING, "message": "Description OK."})
        if self.metadata.get("cta_required") and not cta:
            results.append({"name": "cta_missing", "status": "FAIL", "severity": Severity.CRITICAL, "message": "CTA required but missing."})
        else:
            results.append({"name": "cta_check", "status": "PASS", "severity": Severity.INFO, "message": "CTA check OK."})
        # Nenhuma avaliação de "viralidade"
        return results
