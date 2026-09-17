import { useEffect, useMemo, useState } from "react";
import { Check, Download, Lock, Save } from "lucide-react";
import { api } from "./api.js";
import {
  archiveSvg,
  changeArchiveProfile,
  downloadArchiveSvg,
  medalArtwork,
  normalizeArchive,
} from "./archive.js";
import "./archive.css";

export default function Archive({ data, busy, run, refresh }) {
  const normalized = normalizeArchive(data);
  const [profile, setProfile] = useState(normalized.profile);
  const [feedback, setFeedback] = useState("");
  useEffect(() => setProfile(normalizeArchive(data).profile), [data]);
  const preview = useMemo(
    () => archiveSvg({ ...normalized, profile }),
    [data, profile],
  );
  const toggleMedal = (medal) => {
    if (!medal.earned) return;
    setProfile((current) => {
      const selected_medals = current.selected_medals.includes(medal.id)
        ? current.selected_medals.filter((id) => id !== medal.id)
        : current.selected_medals.length < 3
          ? [...current.selected_medals, medal.id]
          : current.selected_medals;
      return changeArchiveProfile(current, { selected_medals }).profile;
    });
    setFeedback("");
  };
  const changeProfile = (patch) => {
    const next = changeArchiveProfile(profile, patch);
    setProfile(next.profile);
    setFeedback(next.feedback);
  };
  const save = async () => {
    setFeedback("");
    const result = await run(
      () => api.saveArchive(profile),
      (next) => {
        setProfile(normalizeArchive(next).profile);
        setFeedback("已保存到本机档案");
        refresh?.(next);
      },
    );
    if (!result) {
      api
        .archive()
        .then((actual) => {
          setProfile(normalizeArchive(actual).profile);
          refresh?.(actual);
        })
        .catch(() => {});
    }
  };
  return (
    <div className="archive-root" data-theme={profile.theme}>
      <header className="archive-cover">
        <div>
          <span className="archive-kicker">PERSONAL LEARNING ARCHIVE</span>
          <h1>我的档案</h1>
          <p>收藏真实发生过的连接、回顾与重新接通。</p>
        </div>
        <div className="archive-theme" aria-label="档案主题">
          {[
            ["paper", "纸本"],
            ["blueprint", "蓝图"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={profile.theme === id ? "active" : ""}
              onClick={() => changeProfile({ theme: id })}
            >
              {label}
            </button>
          ))}
        </div>
      </header>
      <section className="archive-sheet archive-profile">
        <div>
          <span className="archive-label">ARCHIVE HOLDER</span>
          <h2>档案封面</h2>
        </div>
        <div className="archive-fields">
          <label>
            昵称
            <input
              maxLength={30}
              value={profile.nickname}
              onChange={(e) => changeProfile({ nickname: e.target.value })}
            />
          </label>
          <label>
            签名
            <textarea
              maxLength={100}
              rows={3}
              value={profile.signature}
              onChange={(e) => changeProfile({ signature: e.target.value })}
            />
          </label>
        </div>
      </section>
      <section className="archive-sheet">
        <div className="archive-section-title">
          <div>
            <span className="archive-label">COLLECTED MEDALS</span>
            <h2>勋章架</h2>
          </div>
          <span>已选 {profile.selected_medals.length}/3</span>
        </div>
        <div className="medal-shelf">
          {normalized.medals.map((medal) => (
            <button
              type="button"
              key={medal.id}
              className={`archive-medal ${medal.earned ? "earned" : "locked"} ${profile.selected_medals.includes(medal.id) ? "selected" : ""}`}
              onClick={() => toggleMedal(medal)}
              aria-pressed={profile.selected_medals.includes(medal.id)}
              disabled={!medal.earned}
            >
              <span
                className="medal-art"
                dangerouslySetInnerHTML={{ __html: medalArtwork(medal.id, 72) }}
              />
              {!medal.earned && <Lock size={15} className="medal-lock" />}
              <strong>{medal.title}</strong>
              <small>{medal.description}</small>
              <em>
                {medal.earned
                  ? `获得于 ${medal.earned_at || "已记录"}`
                  : "尚未获得"}
              </em>
              {medal.earned && medal.evidence?.[0]?.date && (
                <span>证据日期 {medal.evidence[0].date}</span>
              )}
            </button>
          ))}
        </div>
      </section>
      <section className="archive-sheet share-section">
        <div className="archive-section-title">
          <div>
            <span className="archive-label">SHARE CARD</span>
            <h2>分享卡</h2>
          </div>
          <label className="stats-toggle">
            <input
              type="checkbox"
              checked={profile.show_stats}
              onChange={(e) => changeProfile({ show_stats: e.target.checked })}
            />
            显示汇总学习数据
          </label>
        </div>
        <p className="archive-privacy">
          预览只包含昵称、签名、已选且已获得的勋章；学习数据需主动勾选。不包含原题、图片或正确率。
        </p>
        <div
          className="share-preview"
          dangerouslySetInnerHTML={{ __html: preview }}
        />
        <div className="archive-actions">
          <button
            className="primary"
            disabled={busy || !profile.nickname.trim()}
            onClick={save}
          >
            <Save size={15} />
            保存档案
          </button>
          <button
            className="secondary"
            onClick={() => downloadArchiveSvg({ ...normalized, profile })}
          >
            <Download size={15} />
            下载 SVG 分享卡
          </button>
          {feedback && (
            <span className="save-feedback">
              <Check size={14} />
              {feedback}
            </span>
          )}
        </div>
      </section>
    </div>
  );
}
