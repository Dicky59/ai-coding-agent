// lib/utils.ts — shared utilities for the dashboard

export function formatDate(isoString: string): string {
  if (!isoString) return "Unknown";
  try {
    return new Date(isoString).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoString;
  }
}

export function getLanguageInfo(language: string): {
  icon: string;
  label: string;
  color: string;
} {
  const map: Record<string, { icon: string; label: string; color: string }> = {
    kotlin:     { icon: "🤖", label: "Kotlin",        color: "bg-purple-900 text-purple-200" },
    java:       { icon: "☕", label: "Java",           color: "bg-orange-900 text-orange-200" },
    typescript: { icon: "📘", label: "TypeScript",     color: "bg-blue-900 text-blue-200"    },
    javascript: { icon: "💛", label: "JavaScript",     color: "bg-yellow-900 text-yellow-200"},
    multi:      { icon: "🌐", label: "Multi-language", color: "bg-green-900 text-green-200"  },
  };
  return map[language] ?? { icon: "📄", label: language, color: "bg-gray-700 text-gray-200" };
}
