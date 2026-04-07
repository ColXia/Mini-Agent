import { useEffect, useMemo, useState } from "react";

import {
  finalizeNovelChapter,
  generateNovelCover,
  generateNovelIllustrations,
  getChapterDiff,
  getChapterVersionContent,
  listChapterVersions,
  listNovelChapters,
  readNovelChapter,
  rollbackChapterVersion,
  saveNovelChapter,
  setupNovel,
  updateChapterVersionMeta,
  writeNovelChapter
} from "../api";
import type { ChapterVersion, NovelChapter } from "../types";

interface NovelStudioModeProps {
  onAssetsDirty: () => void;
}

function parseTagsInput(raw: string): string[] {
  return raw
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function NovelStudioMode({ onAssetsDirty }: NovelStudioModeProps) {
  const [projectDir, setProjectDir] = useState("mini-agent-novel-demo");
  const [topic, setTopic] = useState("失落星港的回声");
  const [genre, setGenre] = useState("太空歌剧");
  const [numChapters, setNumChapters] = useState(12);
  const [wordsPerChapter, setWordsPerChapter] = useState(2200);
  const [dryRun, setDryRun] = useState(false);

  const [chapterNumber, setChapterNumber] = useState(1);
  const [guidance, setGuidance] = useState("本章突出冲突升级与反转钩子。");
  const [chapters, setChapters] = useState<NovelChapter[]>([]);
  const [selectedChapter, setSelectedChapter] = useState<number | null>(null);
  const [editorText, setEditorText] = useState("");
  const [saveNote, setSaveNote] = useState("");
  const [saveTags, setSaveTags] = useState("");

  const [coverPrompt, setCoverPrompt] = useState("赛博悬疑小说封面，雨夜街景，孤独主角，远景城市。");
  const [status, setStatus] = useState("就绪 Ready");
  const [working, setWorking] = useState(false);

  const [versionFinal, setVersionFinal] = useState(false);
  const [versions, setVersions] = useState<ChapterVersion[]>([]);
  const [fromVersion, setFromVersion] = useState("");
  const [toVersion, setToVersion] = useState("");
  const [diffText, setDiffText] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState("");
  const [versionNoteDraft, setVersionNoteDraft] = useState("");
  const [versionTagsDraft, setVersionTagsDraft] = useState("");

  const selectedMeta = useMemo(
    () => chapters.find((chapter) => chapter.chapter === selectedChapter) ?? null,
    [chapters, selectedChapter]
  );
  const selectedVersion = useMemo(
    () => versions.find((version) => version.version_id === selectedVersionId) ?? null,
    [versions, selectedVersionId]
  );

  const loadChapters = async () => {
    const data = await listNovelChapters(projectDir);
    setChapters(data);
    if (!selectedChapter && data.length > 0) {
      setSelectedChapter(data[0].chapter);
    }
  };

  const loadVersions = async (chapter: number, finalFlag = versionFinal) => {
    const data = await listChapterVersions({
      chapter,
      project_dir: projectDir,
      final: finalFlag
    });
    setVersions(data);

    const first = data[0]?.version_id ?? "";
    const latest = data[data.length - 1];
    setFromVersion(first);
    setToVersion(latest?.version_id ?? "");

    if (latest) {
      setSelectedVersionId(latest.version_id);
      setVersionNoteDraft(latest.note ?? "");
      setVersionTagsDraft((latest.tags ?? []).join(", "));
    } else {
      setSelectedVersionId("");
      setVersionNoteDraft("");
      setVersionTagsDraft("");
    }
  };

  useEffect(() => {
    void loadChapters();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedChapter) {
      return;
    }
    void loadVersions(selectedChapter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedChapter, versionFinal]);

  const run = async (label: string, task: () => Promise<void>) => {
    setWorking(true);
    setStatus(`${label}...`);
    try {
      await task();
      setStatus(`${label} 完成`);
    } catch (error) {
      setStatus(`${label} 失败: ${String(error)}`);
    } finally {
      setWorking(false);
    }
  };

  const handleSetup = async () => {
    await run("初始化 Setup", async () => {
      await setupNovel({
        topic,
        genre,
        num_chapters: numChapters,
        words_per_chapter: wordsPerChapter,
        project_dir: projectDir,
        dry_run: dryRun
      });
      await loadChapters();
    });
  };

  const handleWrite = async () => {
    await run("写作 Write", async () => {
      await writeNovelChapter({
        chapter: chapterNumber,
        guidance,
        project_dir: projectDir,
        dry_run: dryRun
      });
      await loadChapters();
      setSelectedChapter(chapterNumber);
      const text = await readNovelChapter(chapterNumber, projectDir);
      setEditorText(text);
      await loadVersions(chapterNumber);
    });
  };

  const handleFinalize = async () => {
    await run("定稿 Finalize", async () => {
      await finalizeNovelChapter({
        chapter: chapterNumber,
        project_dir: projectDir,
        dry_run: dryRun
      });
      await loadChapters();
      await loadVersions(chapterNumber, true);
      onAssetsDirty();
    });
  };

  const handleLoadSelectedChapter = async (final = false) => {
    if (!selectedChapter) {
      return;
    }
    await run(final ? "加载终稿" : "加载草稿", async () => {
      const text = await readNovelChapter(selectedChapter, projectDir, final);
      setEditorText(text);
    });
  };

  const handleSave = async () => {
    if (!selectedChapter) {
      return;
    }
    await run("保存章节 Save", async () => {
      await saveNovelChapter({
        chapter: selectedChapter,
        text: editorText,
        final: versionFinal,
        project_dir: projectDir,
        note: saveNote,
        tags: parseTagsInput(saveTags)
      });
      await loadVersions(selectedChapter, versionFinal);
    });
  };

  const handleCover = async () => {
    await run("生成封面 Cover", async () => {
      await generateNovelCover({
        prompt: coverPrompt,
        output_name: `cover_chapter_${chapterNumber}.png`,
        project_dir: projectDir,
        dry_run: dryRun
      });
      onAssetsDirty();
    });
  };

  const handleIllustrations = async () => {
    await run("生成插图 Illustrations", async () => {
      await generateNovelIllustrations({
        chapter: chapterNumber,
        count: 3,
        project_dir: projectDir,
        dry_run: dryRun
      });
      onAssetsDirty();
    });
  };

  const handleCompareVersions = async () => {
    if (!selectedChapter || !fromVersion || !toVersion) {
      return;
    }
    await run("版本对比 Compare", async () => {
      const diff = await getChapterDiff({
        chapter: selectedChapter,
        from_version: fromVersion,
        to_version: toVersion,
        project_dir: projectDir,
        final: versionFinal
      });
      setDiffText(diff || "无差异输出");
    });
  };

  const selectVersion = (version: ChapterVersion) => {
    setSelectedVersionId(version.version_id);
    setVersionNoteDraft(version.note ?? "");
    setVersionTagsDraft((version.tags ?? []).join(", "));
  };

  const handleLoadVersionToEditor = async (versionId: string) => {
    if (!selectedChapter) {
      return;
    }
    await run("加载版本", async () => {
      const content = await getChapterVersionContent({
        chapter: selectedChapter,
        version_id: versionId,
        project_dir: projectDir,
        final: versionFinal
      });
      setEditorText(content);
      const version = versions.find((item) => item.version_id === versionId);
      if (version) {
        selectVersion(version);
      }
    });
  };

  const handleUpdateVersionMeta = async () => {
    if (!selectedChapter || !selectedVersionId) {
      return;
    }
    await run("更新版本元信息", async () => {
      await updateChapterVersionMeta({
        chapter: selectedChapter,
        version_id: selectedVersionId,
        project_dir: projectDir,
        final: versionFinal,
        note: versionNoteDraft,
        tags: parseTagsInput(versionTagsDraft)
      });
      await loadVersions(selectedChapter, versionFinal);
      setSelectedVersionId(selectedVersionId);
    });
  };

  const handleRollbackVersion = async () => {
    if (!selectedChapter || !selectedVersionId) {
      return;
    }
    await run("版本回滚", async () => {
      const result = await rollbackChapterVersion({
        chapter: selectedChapter,
        version_id: selectedVersionId,
        project_dir: projectDir,
        final: versionFinal
      });
      setEditorText(result.text);
      await loadVersions(selectedChapter, versionFinal);
    });
  };

  return (
    <section className="mode-panel">
      <header className="card top-card">
        <div className="row between">
          <div>
            <h2>小说工坊 Novel Studio（Demo）</h2>
            <p className="muted">支持生成、改稿、版本备注、回滚和素材再生成。</p>
          </div>
          <div className="pill">{status}</div>
        </div>
        <div className="grid-4">
          <label className="field">
            <span>项目目录 Project Dir</span>
            <input value={projectDir} onChange={(event) => setProjectDir(event.target.value)} />
          </label>
          <label className="field">
            <span>主题 Topic</span>
            <input value={topic} onChange={(event) => setTopic(event.target.value)} />
          </label>
          <label className="field">
            <span>类型 Genre</span>
            <input value={genre} onChange={(event) => setGenre(event.target.value)} />
          </label>
          <label className="field">
            <span>试运行 Dry Run</span>
            <select value={String(dryRun)} onChange={(event) => setDryRun(event.target.value === "true")}>
              <option value="false">关闭</option>
              <option value="true">开启</option>
            </select>
          </label>
          <label className="field">
            <span>章节数 Chapters</span>
            <input
              type="number"
              min={1}
              max={200}
              value={numChapters}
              onChange={(event) => setNumChapters(Number(event.target.value))}
            />
          </label>
          <label className="field">
            <span>每章字数 Words / Chapter</span>
            <input
              type="number"
              min={200}
              max={20000}
              value={wordsPerChapter}
              onChange={(event) => setWordsPerChapter(Number(event.target.value))}
            />
          </label>
          <div className="button-row">
            <button type="button" onClick={handleSetup} disabled={working} className="primary-button">
              初始化 Setup
            </button>
            <button type="button" onClick={() => void loadChapters()} disabled={working} className="ghost-button">
              刷新目录 Reload
            </button>
          </div>
        </div>
      </header>

      <section className="card">
        <div className="row wrap">
          <label className="field small">
            <span>章节 Chapter</span>
            <input
              type="number"
              min={1}
              value={chapterNumber}
              onChange={(event) => setChapterNumber(Number(event.target.value))}
            />
          </label>
          <label className="field grow">
            <span>写作引导 Guidance</span>
            <input value={guidance} onChange={(event) => setGuidance(event.target.value)} />
          </label>
          <div className="button-row">
            <button type="button" onClick={handleWrite} disabled={working} className="primary-button">
              写作 Write
            </button>
            <button type="button" onClick={handleFinalize} disabled={working} className="ghost-button">
              定稿 Finalize
            </button>
          </div>
        </div>
        <div className="row wrap">
          <label className="field grow">
            <span>封面提示词 Cover Prompt</span>
            <input value={coverPrompt} onChange={(event) => setCoverPrompt(event.target.value)} />
          </label>
          <div className="button-row">
            <button type="button" onClick={handleCover} disabled={working} className="ghost-button">
              生成封面 Cover
            </button>
            <button type="button" onClick={handleIllustrations} disabled={working} className="ghost-button">
              生成插图 Illustrations
            </button>
          </div>
        </div>
      </section>

      <div className="split-grid">
        <section className="card chapter-list">
          <div className="row between">
            <h3>章节目录 Chapter Index</h3>
            <span className="muted">{chapters.length} 项</span>
          </div>
          <div className="chapter-scroll">
            {chapters.length === 0 ? <p className="empty">暂无章节，请先初始化小说项目。</p> : null}
            {chapters.map((chapter) => (
              <button
                key={chapter.chapter}
                type="button"
                className={`chapter-item ${selectedChapter === chapter.chapter ? "active" : ""}`}
                onClick={() => setSelectedChapter(chapter.chapter)}
              >
                <strong>
                  {chapter.chapter}. {chapter.title}
                </strong>
                <small>{chapter.summary}</small>
                <small>
                  草稿 draft: {String(Boolean(chapter.draft_exists))} | 终稿 final:{" "}
                  {String(Boolean(chapter.final_exists))}
                </small>
              </button>
            ))}
          </div>
        </section>

        <section className="card">
          <div className="row between">
            <h3>编辑器 Editor {selectedMeta ? `#${selectedMeta.chapter}` : ""}</h3>
            <div className="button-row">
              <button type="button" onClick={() => void handleLoadSelectedChapter(false)} className="ghost-button">
                加载草稿
              </button>
              <button type="button" onClick={() => void handleLoadSelectedChapter(true)} className="ghost-button">
                加载终稿
              </button>
              <button type="button" onClick={handleSave} className="primary-button">
                保存 Save
              </button>
            </div>
          </div>
          <div className="row wrap">
            <label className="field grow">
              <span>保存备注 Save Note</span>
              <input
                value={saveNote}
                onChange={(event) => setSaveNote(event.target.value)}
                placeholder="本次保存说明"
              />
            </label>
            <label className="field grow">
              <span>保存标签 Save Tags（逗号分隔）</span>
              <input
                value={saveTags}
                onChange={(event) => setSaveTags(event.target.value)}
                placeholder="draft,revise,hook"
              />
            </label>
          </div>
          <textarea
            className="editor"
            value={editorText}
            onChange={(event) => setEditorText(event.target.value)}
            placeholder="章节内容会显示在这里，支持反复改稿。"
          />
        </section>
      </div>

      <section className="card">
        <div className="row between">
          <h3>版本差异 Version Diff</h3>
          <div className="button-row">
            <label className="field small">
              <span>轨道 Track</span>
              <select value={String(versionFinal)} onChange={(event) => setVersionFinal(event.target.value === "true")}>
                <option value="false">草稿 Draft</option>
                <option value="true">终稿 Final</option>
              </select>
            </label>
            <button
              type="button"
              onClick={() => selectedChapter && void loadVersions(selectedChapter)}
              disabled={!selectedChapter}
              className="ghost-button"
            >
              刷新版本 Reload
            </button>
          </div>
        </div>

        <div className="row wrap">
          <label className="field grow">
            <span>起始版本 From Version</span>
            <select value={fromVersion} onChange={(event) => setFromVersion(event.target.value)}>
              <option value="">请选择...</option>
              {versions.map((version) => (
                <option key={`from-${version.version_id}`} value={version.version_id}>
                  {version.created_at} | {version.source} | {version.version_id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <label className="field grow">
            <span>目标版本 To Version</span>
            <select value={toVersion} onChange={(event) => setToVersion(event.target.value)}>
              <option value="">请选择...</option>
              {versions.map((version) => (
                <option key={`to-${version.version_id}`} value={version.version_id}>
                  {version.created_at} | {version.source} | {version.version_id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <div className="button-row">
            <button
              type="button"
              onClick={handleCompareVersions}
              disabled={!fromVersion || !toVersion}
              className="primary-button"
            >
              对比 Compare
            </button>
          </div>
        </div>

        <div className="version-list">
          {versions.length === 0 ? <p className="empty">暂无版本记录。</p> : null}
          {versions.map((version) => (
            <button
              key={version.version_id}
              type="button"
              className={`version-item ${selectedVersionId === version.version_id ? "active" : ""}`}
              onClick={() => {
                selectVersion(version);
                void handleLoadVersionToEditor(version.version_id);
              }}
            >
              <strong>{version.version_id.slice(0, 12)}</strong>
              <span>{version.created_at}</span>
              <span>
                {version.source} | {version.content_length} 字符
              </span>
              <span>
                tags: {(version.tags ?? []).join(", ") || "-"} | note: {version.note || "-"}
              </span>
            </button>
          ))}
        </div>

        <div className="version-meta-box">
          <h4>版本元信息 Version Meta</h4>
          <p className="muted">
            {selectedVersion ? `当前选中: ${selectedVersion.version_id}` : "请先选择一个版本。"}
          </p>
          <div className="row wrap">
            <label className="field grow">
              <span>备注 Note</span>
              <input
                value={versionNoteDraft}
                onChange={(event) => setVersionNoteDraft(event.target.value)}
                placeholder="版本备注"
                disabled={!selectedVersionId}
              />
            </label>
            <label className="field grow">
              <span>标签 Tags（逗号分隔）</span>
              <input
                value={versionTagsDraft}
                onChange={(event) => setVersionTagsDraft(event.target.value)}
                placeholder="rewrite,important"
                disabled={!selectedVersionId}
              />
            </label>
            <div className="button-row">
              <button
                type="button"
                onClick={handleUpdateVersionMeta}
                disabled={!selectedVersionId}
                className="ghost-button"
              >
                保存元信息
              </button>
              <button
                type="button"
                onClick={handleRollbackVersion}
                disabled={!selectedVersionId}
                className="warn-button"
              >
                回滚 Rollback
              </button>
            </div>
          </div>
        </div>

        <pre className="diff-box">{diffText || "暂无差异输出"}</pre>
      </section>
    </section>
  );
}
