import type { ChapterVersion, NovelAsset, NovelChapter } from "../types";
import { appendOptionalQuery, request } from "./client";

export async function setupNovel(payload: {
  topic: string;
  genre: string;
  num_chapters: number;
  words_per_chapter: number;
  project_dir?: string;
  dry_run?: boolean;
}): Promise<{ status: string }> {
  return request<{ status: string }>("/api/v1/novel/setup", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function writeNovelChapter(payload: {
  chapter: number;
  guidance: string;
  project_dir?: string;
  dry_run?: boolean;
}): Promise<{ status: string }> {
  return request<{ status: string }>("/api/v1/novel/write", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function finalizeNovelChapter(payload: {
  chapter: number;
  project_dir?: string;
  dry_run?: boolean;
}): Promise<{ status: string }> {
  return request<{ status: string }>("/api/v1/novel/finalize", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function generateNovelCover(payload: {
  prompt: string;
  output_name: string;
  project_dir?: string;
  dry_run?: boolean;
}): Promise<{ status: string; url: string }> {
  return request<{ status: string; url: string }>("/api/v1/novel/cover", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function generateNovelIllustrations(payload: {
  chapter: number;
  count: number;
  project_dir?: string;
  dry_run?: boolean;
}): Promise<{ status: string; urls: string[] }> {
  return request<{ status: string; urls: string[] }>("/api/v1/novel/illustrate", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listNovelChapters(project_dir?: string): Promise<NovelChapter[]> {
  const query = project_dir ? `?project_dir=${encodeURIComponent(project_dir)}` : "";
  const data = await request<{ chapters: NovelChapter[] }>(`/api/v1/novel/chapters${query}`);
  return data.chapters ?? [];
}

export async function readNovelChapter(chapter: number, project_dir?: string, final = false): Promise<string> {
  const search = new URLSearchParams();
  if (project_dir) {
    search.set("project_dir", project_dir);
  }
  if (final) {
    search.set("final", "true");
  }
  const suffix = search.toString();
  const data = await request<{ text: string }>(`/api/v1/novel/chapter/${chapter}${suffix ? `?${suffix}` : ""}`);
  return data.text ?? "";
}

export async function saveNovelChapter(payload: {
  chapter: number;
  text: string;
  final?: boolean;
  project_dir?: string;
  note?: string;
  tags?: string[];
}): Promise<{ status: string; version?: ChapterVersion }> {
  const { chapter, ...body } = payload;
  return request<{ status: string; version?: ChapterVersion }>(`/api/v1/novel/chapter/${chapter}`, {
    method: "PUT",
    body: JSON.stringify(body)
  });
}

export async function listChapterVersions(payload: {
  chapter: number;
  project_dir?: string;
  final?: boolean;
}): Promise<ChapterVersion[]> {
  const search = new URLSearchParams();
  if (payload.project_dir) {
    search.set("project_dir", payload.project_dir);
  }
  if (payload.final) {
    search.set("final", "true");
  }
  const query = search.toString();
  const data = await request<{ versions: ChapterVersion[] }>(
    `/api/v1/novel/chapter/${payload.chapter}/versions${query ? `?${query}` : ""}`
  );
  return data.versions ?? [];
}

export async function getChapterVersionContent(payload: {
  chapter: number;
  version_id: string;
  project_dir?: string;
  final?: boolean;
}): Promise<string> {
  const search = new URLSearchParams();
  if (payload.project_dir) {
    search.set("project_dir", payload.project_dir);
  }
  if (payload.final) {
    search.set("final", "true");
  }
  const query = search.toString();
  const data = await request<{ content: string }>(
    `/api/v1/novel/chapter/${payload.chapter}/version/${payload.version_id}${query ? `?${query}` : ""}`
  );
  return data.content ?? "";
}

export async function updateChapterVersionMeta(payload: {
  chapter: number;
  version_id: string;
  project_dir?: string;
  final?: boolean;
  note?: string;
  tags?: string[];
}): Promise<ChapterVersion> {
  const { chapter, version_id, ...body } = payload;
  const data = await request<{ version: ChapterVersion }>(`/api/v1/novel/chapter/${chapter}/version/${version_id}`, {
    method: "PATCH",
    body: JSON.stringify(body)
  });
  return data.version;
}

export async function rollbackChapterVersion(payload: {
  chapter: number;
  version_id: string;
  project_dir?: string;
  final?: boolean;
  note?: string;
  tags?: string[];
}): Promise<{ text: string; version: ChapterVersion; restored_from_version: ChapterVersion }> {
  const { chapter, ...body } = payload;
  return request<{ text: string; version: ChapterVersion; restored_from_version: ChapterVersion }>(
    `/api/v1/novel/chapter/${chapter}/rollback`,
    {
      method: "POST",
      body: JSON.stringify(body)
    }
  );
}

export async function getChapterDiff(payload: {
  chapter: number;
  from_version: string;
  to_version: string;
  project_dir?: string;
  final?: boolean;
}): Promise<string> {
  const search = new URLSearchParams();
  search.set("from_version", payload.from_version);
  search.set("to_version", payload.to_version);
  if (payload.project_dir) {
    search.set("project_dir", payload.project_dir);
  }
  if (payload.final) {
    search.set("final", "true");
  }
  const data = await request<{ diff: string }>(`/api/v1/novel/chapter/${payload.chapter}/diff?${search.toString()}`);
  return data.diff ?? "";
}

export async function listNovelAssets(project_dir?: string): Promise<NovelAsset[]> {
  const path = appendOptionalQuery("/api/v1/novel/assets", { project_dir });
  const data = await request<{ assets: NovelAsset[] }>(path);
  return data.assets ?? [];
}
