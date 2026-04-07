import { useEffect, useMemo, useState } from "react";

import { getApiBase, listNovelAssets } from "../api";
import type { NovelAsset } from "../types";

interface AssetsModeProps {
  refreshNonce: number;
}

export function AssetsMode({ refreshNonce }: AssetsModeProps) {
  const [projectDir, setProjectDir] = useState("mini-agent-novel-demo");
  const [assets, setAssets] = useState<NovelAsset[]>([]);
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState("");

  const grouped = useMemo(() => {
    return {
      covers: assets.filter((item) => item.asset_type === "covers"),
      illustrations: assets.filter((item) => item.asset_type === "illustrations"),
      audio: assets.filter((item) => item.asset_type === "audio")
    };
  }, [assets]);

  const loadAssets = async () => {
    setLoading(true);
    setErrorText("");
    try {
      const data = await listNovelAssets(projectDir);
      setAssets(data);
    } catch (error) {
      setErrorText(String(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAssets();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshNonce]);

  const renderAsset = (asset: NovelAsset) => {
    const absoluteUrl = `${getApiBase()}${asset.url}`;
    if (asset.name.endsWith(".png") || asset.name.endsWith(".jpg") || asset.name.endsWith(".jpeg")) {
      return <img src={absoluteUrl} alt={asset.name} />;
    }
    if (asset.name.endsWith(".mp3") || asset.name.endsWith(".wav")) {
      return <audio controls src={absoluteUrl} />;
    }
    return (
      <a href={absoluteUrl} target="_blank" rel="noreferrer">
        打开文件 {asset.name}
      </a>
    );
  };

  return (
    <section className="mode-panel">
      <header className="card top-card">
        <div className="row between">
          <div>
            <h2>素材库</h2>
            <p className="muted">封面、插图、音频统一预览，便于快速检查输出质量。</p>
          </div>
          <div className="pill">{loading ? "加载中..." : `${assets.length} 个文件`}</div>
        </div>
        <div className="row wrap">
          <label className="field grow">
            <span>项目目录</span>
            <input value={projectDir} onChange={(event) => setProjectDir(event.target.value)} />
          </label>
          <button type="button" onClick={() => void loadAssets()} className="primary-button">
            刷新
          </button>
        </div>
        {errorText ? <p className="error-text">{errorText}</p> : null}
      </header>

      <div className="asset-section card">
        <h3>封面</h3>
        <div className="asset-grid">
          {grouped.covers.length === 0 ? <p className="empty">暂无封面素材。</p> : null}
          {grouped.covers.map((asset) => (
            <article key={asset.path} className="asset-card">
              {renderAsset(asset)}
              <p>{asset.name}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="asset-section card">
        <h3>插图</h3>
        <div className="asset-grid">
          {grouped.illustrations.length === 0 ? <p className="empty">暂无插图素材。</p> : null}
          {grouped.illustrations.map((asset) => (
            <article key={asset.path} className="asset-card">
              {renderAsset(asset)}
              <p>{asset.name}</p>
            </article>
          ))}
        </div>
      </div>

      <div className="asset-section card">
        <h3>音频</h3>
        <div className="asset-grid">
          {grouped.audio.length === 0 ? <p className="empty">暂无音频素材。</p> : null}
          {grouped.audio.map((asset) => (
            <article key={asset.path} className="asset-card">
              {renderAsset(asset)}
              <p>{asset.name}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
