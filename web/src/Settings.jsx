import { useState } from "react";
import { Plus, Trash2, Check } from "lucide-react";
import { api } from "./api.js";
import { Modal } from "./ui.jsx";

const newProfile = (name = "新模型") => ({
  id: crypto.randomUUID(),
  name,
  base_url: "https://api.openai.com/v1",
  model: "",
  api_key: "",
  has_key: false,
});
const roles = { vision: "图片识别", solve: "题目解答", chat: "学习对话" };

export default function Settings({ initial, busy, run, onClose }) {
  const [value, setValue] = useState(() => {
    const profiles = initial.profiles?.length
      ? initial.profiles
      : [newProfile("学习模型")];
    return {
      ...initial,
      profiles,
      tasks: Object.fromEntries(
        Object.keys(roles).map((key) => [
          key,
          initial.tasks?.[key] ||
            profiles[key === "vision" ? 0 : profiles.length - 1].id,
        ]),
      ),
      mode: "direct",
    };
  });
  const [notice, setNotice] = useState(""),
    [active, setActive] = useState(value.profiles[0]?.id);
  const patch = (id, update) =>
    setValue((v) => ({
      ...v,
      profiles: v.profiles.map((p) => (p.id === id ? { ...p, ...update } : p)),
    }));
  const remove = (id) =>
    setValue((v) => {
      const profiles = v.profiles.filter((p) => p.id !== id);
      setActive(profiles[0]?.id);
      return {
        ...v,
        profiles,
        tasks: Object.fromEntries(
          Object.entries(v.tasks).map(([key, pid]) => [
            key,
            pid === id ? profiles[0]?.id || "" : pid,
          ]),
        ),
      };
    });
  const save = async (close) => {
    const result = await run(() =>
      api.saveSettings({ ...value, mode: "direct" }),
    );
    if (result) {
      setValue(result);
      if (close) onClose();
      else setNotice("设置已保存。");
    }
    return result;
  };
  const p = value.profiles.find((p) => p.id === active);
  return (
    <Modal title="模型设置" onClose={onClose} wide>
      <div className="modal-body settings-body">
        <p className="muted">
          连接你自己的模型，为图片识别、解题和追问分别分配任务。
        </p>
        <div className="profile-tabs">
          {value.profiles.map((p) => (
            <button
              className={p.id === active ? "active" : ""}
              key={p.id}
              onClick={() => setActive(p.id)}
            >
              {p.name || "未命名模型"}
              {p.has_key && <Check size={12} />}
            </button>
          ))}
          <button
            aria-label="添加模型"
            onClick={() => {
              const p = newProfile();
              setValue((v) => ({ ...v, profiles: [...v.profiles, p] }));
              setActive(p.id);
            }}
          >
            <Plus size={15} />
          </button>
        </div>
        {p && (
          <section className="profile-card">
            <div className="form-grid">
              <label>
                显示名称
                <input
                  value={p.name || ""}
                  onChange={(e) => patch(p.id, { name: e.target.value })}
                />
              </label>
              <label>
                模型名称
                <input
                  value={p.model || ""}
                  placeholder="例如 gpt-4.1"
                  onChange={(e) => patch(p.id, { model: e.target.value })}
                />
              </label>
              <label className="span-two">
                接口地址
                <input
                  value={p.base_url || ""}
                  placeholder="https://api.openai.com/v1"
                  onChange={(e) => patch(p.id, { base_url: e.target.value })}
                />
              </label>
              <label className="span-two">
                API Key
                <input
                  type="password"
                  autoComplete="new-password"
                  value={p.api_key || ""}
                  placeholder={
                    p.has_key ? "已保存，留空保留现有密钥" : "输入密钥"
                  }
                  onChange={(e) =>
                    patch(p.id, { api_key: e.target.value, remove_key: false })
                  }
                />
              </label>
              <label>
                并发上限
                <input
                  type="number"
                  min="1"
                  max="8"
                  value={p.parallel ?? ""}
                  placeholder="沿用全局"
                  onChange={(e) =>
                    patch(p.id, {
                      parallel: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                />
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={!!p.disable_thinking}
                  onChange={(e) =>
                    patch(p.id, { disable_thinking: e.target.checked })
                  }
                />
                关闭深度思考
              </label>
            </div>
            <div className="profile-actions">
              <button
                className="text-button"
                disabled={busy || !p.model}
                onClick={async () => {
                  if (await save(false))
                    await run(
                      () => api.testProfile(p.id),
                      (result) =>
                        setNotice(
                          result.message ||
                            (result.ok ? "连接成功" : "测试完成"),
                        ),
                    );
                }}
              >
                保存并测试连接
              </button>
              {p.has_key && (
                <button
                  className="text-button danger-text"
                  onClick={() =>
                    patch(p.id, {
                      remove_key: true,
                      api_key: "",
                      has_key: false,
                    })
                  }
                >
                  移除密钥
                </button>
              )}
              <button
                className="icon-button danger-text"
                aria-label={`删除模型 ${p.name}`}
                onClick={() => remove(p.id)}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </section>
        )}
        <h3 className="section-heading">任务分配</h3>
        <div className="task-grid">
          {Object.entries(roles).map(([key, label]) => (
            <label key={key}>
              {label}
              <select
                value={value.tasks?.[key] || ""}
                onChange={(e) =>
                  setValue((v) => ({
                    ...v,
                    tasks: { ...v.tasks, [key]: e.target.value },
                  }))
                }
              >
                <option value="">未配置</option>
                {value.profiles.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <details className="advanced">
          <summary>请求速率与并发</summary>
          <div className="form-grid">
            <label>
              每分钟 Token 上限
              <input
                type="number"
                min="1000"
                placeholder="默认 15000"
                value={value.rate_tpm ?? ""}
                onChange={(e) =>
                  setValue((v) => ({
                    ...v,
                    rate_tpm: e.target.value ? Number(e.target.value) : null,
                  }))
                }
              />
            </label>
            <label>
              全局并发
              <input
                type="number"
                min="1"
                max="8"
                value={value.parallel ?? 2}
                onChange={(e) =>
                  setValue((v) => ({ ...v, parallel: Number(e.target.value) }))
                }
              />
            </label>
          </div>
        </details>
        {notice && (
          <p className="notice" role="status">
            {notice}
          </p>
        )}
      </div>
      <footer className="modal-footer">
        <span className="muted small">密钥保存在本机，不返回网页。</span>
        <button className="secondary" disabled={busy} onClick={onClose}>
          取消
        </button>
        <button className="primary" disabled={busy} onClick={() => save(true)}>
          保存设置
        </button>
      </footer>
    </Modal>
  );
}
