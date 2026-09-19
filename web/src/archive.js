export const ARCHIVE_THEMES = ["paper", "blueprint"];

export function changeArchiveProfile(profile, patch) {
  return { profile: { ...profile, ...patch }, feedback: "" };
}

export function rejectedArchiveProfile(profile) {
  return { ...profile, selected_medals: [] };
}

export async function recoverRejectedArchive(profile, fetchArchive) {
  const safeProfile = rejectedArchiveProfile(profile);
  try {
    const data = await fetchArchive();
    return { profile: normalizeArchive(data).profile, data, error: "" };
  } catch {
    return {
      profile: safeProfile,
      data: null,
      error: "勋章资格暂时无法刷新；已清空未核对的选择，请稍后重试。",
    };
  }
}

export function acceptedArchiveSave(data) {
  return { profile: normalizeArchive(data).profile, data, error: "" };
}

export function normalizeArchive(data = {}) {
  const profile = data.profile || {};
  const medals = Array.isArray(data.medals) ? data.medals : [];
  const earned = new Set(
    medals.filter((medal) => medal.earned).map((medal) => medal.id),
  );
  return {
    profile: {
      nickname: String(
        Object.prototype.hasOwnProperty.call(profile, "nickname")
          ? profile.nickname
          : "学习者",
      ).slice(0, 30),
      signature: String(profile.signature || "").slice(0, 100),
      theme: ARCHIVE_THEMES.includes(profile.theme) ? profile.theme : "paper",
      selected_medals: [...new Set(profile.selected_medals || [])]
        .filter((id) => earned.has(id))
        .slice(0, 3),
      show_stats: profile.show_stats === true,
    },
    stats: {
      questions: Number(data.stats?.questions || 0),
      linked_nodes: Number(data.stats?.linked_nodes || 0),
      review_days: Number(data.stats?.review_days || 0),
    },
    medals,
  };
}

const escapeXml = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&apos;",
      })[char],
  );
const glyphWidth = (char) => (/^[\x00-\xff]$/.test(char) ? 0.56 : 1);
export const estimatedTextWidth = (value, fontSize) =>
  [...String(value || "")].reduce(
    (sum, char) => sum + glyphWidth(char) * fontSize,
    0,
  );
export function wrapText(value, maxWidth, maxLines = 1) {
  const chars = [...String(value || "")];
  const lines = [];
  let line = "",
    width = 0;
  while (chars.length && lines.length < maxLines) {
    const char = chars.shift(),
      next = width + glyphWidth(char);
    if (line && next > maxWidth) {
      lines.push(line);
      line = "";
      width = 0;
      chars.unshift(char);
    } else {
      line += char;
      width = next;
    }
  }
  if (line && lines.length < maxLines) lines.push(line);
  if (chars.length && lines.length) {
    let last = lines.at(-1);
    while (
      last &&
      [...last].reduce((sum, char) => sum + glyphWidth(char), 0) + 1 > maxWidth
    )
      last = [...last].slice(0, -1).join("");
    lines[lines.length - 1] = `${last}…`;
  }
  return lines.length ? lines : [""];
}
const textLines = (value, x, firstY, lineHeight, maxWidth, maxLines) =>
  wrapText(value, maxWidth, maxLines)
    .map(
      (line, index) =>
        `<tspan x="${x}" y="${firstY + index * lineHeight}">${escapeXml(line)}</tspan>`,
    )
    .join("");

export function medalArtwork(id, size = 54) {
  if (id === "next_day")
    return `<svg viewBox="0 0 64 64" width="${size}" height="${size}" aria-hidden="true"><circle cx="32" cy="32" r="27" fill="none" stroke="currentColor" stroke-width="2"/><path d="M20 38h24M23 25h18v18H23zM27 20v9M37 20v9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M29 34h6" stroke="currentColor" stroke-width="3"/></svg>`;
  if (id === "reconnected")
    return `<svg viewBox="0 0 64 64" width="${size}" height="${size}" aria-hidden="true"><circle cx="32" cy="32" r="27" fill="none" stroke="currentColor" stroke-width="2"/><path d="M18 34h10l4-9 5 17 4-8h6" fill="none" stroke="currentColor" stroke-width="2.5"/><path d="M18 22v-4h8M46 42v4h-8" fill="none" stroke="currentColor" stroke-width="2"/></svg>`;
  return `<svg viewBox="0 0 64 64" width="${size}" height="${size}" aria-hidden="true"><circle cx="32" cy="32" r="27" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="23" cy="32" r="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="41" cy="23" r="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="41" cy="41" r="5" fill="none" stroke="currentColor" stroke-width="2"/><path d="m27 30 9-5m-9 9 9 5" stroke="currentColor" stroke-width="2"/></svg>`;
}

export function archiveSvg(input) {
  const { profile, stats, medals } = normalizeArchive(input);
  const palette =
    profile.theme === "blueprint"
      ? { bg: "#102b48", ink: "#eefbff", line: "#62c7dc", soft: "#173b5f" }
      : { bg: "#f3ead7", ink: "#3f3429", line: "#9c694f", soft: "#e8dcc5" };
  const selected = profile.selected_medals
    .map((id) => medals.find((m) => m.id === id))
    .filter(Boolean);
  const medalRows = selected.length
    ? selected
        .map(
          (m, i) =>
            `<g transform="translate(${70 + i * 190} 300)" color="${palette.line}">${medalArtwork(m.id, 64)}<text x="32" y="84" text-anchor="middle" fill="${palette.ink}" font-size="15">${escapeXml(wrapText(m.title, 10, 1)[0])}</text></g>`,
        )
        .join("")
    : `<text x="60" y="350" fill="${palette.ink}" opacity=".65" font-size="18">勋章席位留给下一次认真的学习</text>`;
  const statsRow = profile.show_stats
    ? `<g transform="translate(60 465)" fill="${palette.ink}" font-size="15"><text x="0">已核对题目 ${stats.questions}</text><text x="190">已连接节点 ${stats.linked_nodes}</text><text x="380">复习日 ${stats.review_days}</text></g>`
    : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="520" viewBox="0 0 640 520" role="img" aria-label="个人学习档案分享卡"><rect width="640" height="520" rx="28" fill="${palette.bg}"/><path d="M42 78h556M42 444h556" stroke="${palette.line}" opacity=".7"/><text x="60" y="62" fill="${palette.line}" font-size="12" letter-spacing="3">PERSONAL LEARNING ARCHIVE</text><text fill="${palette.ink}" font-size="38" font-family="Songti SC,STSong,serif">${textLines(profile.nickname, 60, 145, 42, 13, 1)}</text><text fill="${palette.ink}" opacity=".78" font-size="17" font-family="PingFang SC,Microsoft YaHei,sans-serif">${textLines(profile.signature, 60, 190, 24, 29, 2)}</text><text x="60" y="260" fill="${palette.line}" font-size="12" letter-spacing="2">COLLECTED MEDALS</text>${medalRows}${statsRow}</svg>`;
}

export function downloadArchiveSvg(
  data,
  documentRef = document,
  urlApi = URL,
  defer = (callback) => setTimeout(callback, 0),
) {
  const blob = new Blob([archiveSvg(data)], {
    type: "image/svg+xml;charset=utf-8",
  });
  const url = urlApi.createObjectURL(blob);
  const link = documentRef.createElement("a");
  link.href = url;
  link.download = "我的学习档案.svg";
  documentRef.body.appendChild(link);
  link.click();
  link.remove();
  defer(() => urlApi.revokeObjectURL(url));
}
