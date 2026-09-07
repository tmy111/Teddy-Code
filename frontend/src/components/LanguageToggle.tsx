import { useI18n, type Language } from "../i18n";

const options: Array<{ value: Language; label: string }> = [
  { value: "zh", label: "中文" },
  { value: "en", label: "EN" },
];

export function LanguageToggle() {
  const { language, setLanguage, t } = useI18n();

  return (
    <div className="language-toggle" role="group" aria-label={t("languageSwitcher")}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={language === option.value ? "active" : ""}
          aria-pressed={language === option.value}
          onClick={() => setLanguage(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
