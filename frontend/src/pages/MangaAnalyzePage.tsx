import { useEffect, useMemo, useState } from 'react'
import {
  Alert, Button, Card, Col, Descriptions, Form, Input, Progress, Row,
  Select, Space, Steps, Table, Tabs, Tag, Typography, Upload, message,
} from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import {
  DownloadOutlined, FileSearchOutlined, InboxOutlined,
} from '@ant-design/icons'
import { listProjects, uploadManga, analyzeManga, openJobWS } from '../api'
import type { Project, Job } from '../types'

const { Title, Paragraph, Text } = Typography
const { Dragger } = Upload

interface Character {
  name: string
  role?: string
  appearance?: string
  costume?: string
  personality?: string
  voice_tone?: string
  first_appear_panel?: number
}
interface Act {
  name: string
  panels_range?: [number, number]
  summary?: string
}
interface Shot {
  index: number
  page?: number
  panel_order?: number
  timecode?: string
  duration?: number
  shot_type?: string
  camera_motion?: string
  environment?: {
    location?: string
    time_of_day?: string
    weather?: string
    lighting?: string
    details?: string
  }
  characters_in_shot?: {
    name: string
    costume?: string
    action?: string
    expression?: string
    emotion?: string
  }[]
  dialogue?: string
  speaker?: string
  sfx?: string
  image_prompt?: string
  video_prompt?: string
  panel_image_url?: string
}
interface Report {
  title?: string
  genre?: string
  summary?: string
  tone?: string
  bgm_hint?: string
  notes?: string
  characters?: Character[]
  script?: { acts?: Act[] }
  storyboard?: Shot[]
  _meta?: Record<string, any>
  _fallback?: boolean
}

export default function MangaAnalyzePage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<string>()
  const [files, setFiles] = useState<UploadFile[]>([])
  const [uploadId, setUploadId] = useState<string>()
  const [style, setStyle] = useState<string>('日系动画')
  const [extraHint, setExtraHint] = useState<string>('')
  const [job, setJob] = useState<Job | null>(null)
  const [step, setStep] = useState(0)

  useEffect(() => { listProjects().then(setProjects) }, [])

  const onUpload = async () => {
    if (!projectId) { message.warning('先选择项目'); return }
    if (!files.length) { message.warning('先选择文件'); return }
    const f = files[0].originFileObj as File
    const r = await uploadManga(projectId, f)
    setUploadId(r.id)
    message.success('漫画已上传')
    setStep(1)
  }

  const onAnalyze = async () => {
    if (!projectId || !uploadId) return
    const j = await analyzeManga({
      project_id: projectId,
      upload_id: uploadId,
      style,
      extra_hint: extraHint || undefined,
      shot_duration: 4.0,
    })
    setJob(j)
    setStep(2)
    const ws = openJobWS(j.id, (snap) => {
      setJob((prev) => prev ? { ...prev, ...snap } : prev)
    })
    return () => ws.close()
  }

  const report: Report = useMemo(() => (job?.result as Report) || {}, [job])
  const done = job?.status === 'success'

  // ---------- Markdown export ----------
  const toMarkdown = (r: Report): string => {
    const lines: string[] = []
    lines.push(`# ${r.title || '漫画拆解报告'}`)
    if (r.genre) lines.push(`\n**类型**：${r.genre}`)
    if (r.summary) lines.push(`\n**概要**：${r.summary}`)
    if (r.tone) lines.push(`\n**氛围**：${r.tone}`)
    if (r.bgm_hint) lines.push(`\n**BGM 建议**：${r.bgm_hint}`)

    lines.push(`\n\n## 👥 角色设定\n`)
    for (const c of (r.characters || [])) {
      lines.push(`### ${c.name}${c.role ? `（${c.role}）` : ''}`)
      if (c.appearance) lines.push(`- 外貌：${c.appearance}`)
      if (c.costume) lines.push(`- 服装：${c.costume}`)
      if (c.personality) lines.push(`- 性格：${c.personality}`)
      if (c.voice_tone) lines.push(`- 声线：${c.voice_tone}`)
      if (c.first_appear_panel != null) lines.push(`- 首次出场：第 ${c.first_appear_panel} 格`)
      lines.push('')
    }

    lines.push(`\n## 🎭 剧本结构\n`)
    for (const a of (r.script?.acts || [])) {
      const rng = a.panels_range ? `（${a.panels_range[0]}-${a.panels_range[1]}）` : ''
      lines.push(`### ${a.name}${rng}`)
      if (a.summary) lines.push(a.summary)
      lines.push('')
    }

    lines.push(`\n## 🎬 分镜列表\n`)
    for (const s of (r.storyboard || [])) {
      lines.push(`### 分镜 #${s.index} ｜ ${s.timecode || ''} ｜ ${s.shot_type || ''} ｜ ${s.camera_motion || ''}`)
      if (s.environment) {
        const e = s.environment
        lines.push(`- 环境：${[e.location, e.time_of_day, e.weather, e.lighting, e.details].filter(Boolean).join(' / ')}`)
      }
      for (const ch of (s.characters_in_shot || [])) {
        lines.push(`- 角色 **${ch.name}**：${[ch.costume && '穿'+ch.costume, ch.action, ch.expression, ch.emotion && '情绪:'+ch.emotion].filter(Boolean).join(' / ')}`)
      }
      if (s.dialogue) lines.push(`- 台词${s.speaker ? '（'+s.speaker+'）' : ''}：${s.dialogue}`)
      if (s.sfx) lines.push(`- 音效：${s.sfx}`)
      if (s.image_prompt) lines.push(`- 图像 prompt：\n\n\`\`\`\n${s.image_prompt}\n\`\`\``)
      if (s.video_prompt) lines.push(`- 视频 prompt：\n\n\`\`\`\n${s.video_prompt}\n\`\`\``)
      lines.push('')
    }

    if (r.notes) {
      lines.push(`\n## 📝 制作备注\n\n${r.notes}`)
    }
    return lines.join('\n')
  }

  const onExport = () => {
    const md = toMarkdown(report)
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `manga-analysis-${(report.title || 'untitled').replace(/\s+/g, '_')}.md`
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(a.href)
  }

  const onExportJson = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `manga-analysis-${(report.title || 'untitled').replace(/\s+/g, '_')}.json`
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
    URL.revokeObjectURL(a.href)
  }

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      <Title level={3} style={{ color: '#fff' }}>📑 漫画深度剖析</Title>
      <Paragraph type="secondary">
        上传静态漫画 → 自动分格 OCR → LLM 拆解为 <b>角色设定 / 剧本结构 / 分镜脚本</b>，
        每个分镜包含 <b>时刻、角色衣着、动作、神态、环境细节、文/图/视频 prompt</b>。
        不生成视频，仅输出可直接使用的制作参考文档（支持导出 Markdown / JSON）。
      </Paragraph>

      <Steps
        current={step}
        items={[
          { title: '上传漫画' }, { title: '参数配置' }, { title: '分析中' }, { title: '查看报告' },
        ]}
        style={{ marginBottom: 24 }}
      />

      {step === 0 && (
        <Card>
          <Form layout="vertical">
            <Form.Item label="所属项目" required>
              <Select
                placeholder="选择项目"
                value={projectId}
                onChange={setProjectId}
                options={projects.map((p) => ({ value: p.id, label: p.name }))}
              />
            </Form.Item>
            <Form.Item label="漫画文件">
              <Dragger
                beforeUpload={() => false}
                fileList={files}
                onChange={({ fileList }) => setFiles(fileList.slice(-1))}
                maxCount={1}
                accept=".pdf,.png,.jpg,.jpeg,.webp,.zip"
              >
                <p className="ant-upload-drag-icon"><InboxOutlined /></p>
                <p>点击或拖拽文件到此区域上传</p>
                <p style={{ color: '#999' }}>支持 PDF / 长条漫 / 多图 ZIP，单文件 ≤ 500MB</p>
              </Dragger>
            </Form.Item>
            <Button type="primary" block onClick={onUpload} disabled={!files.length || !projectId}>
              下一步：上传并解析
            </Button>
          </Form>
        </Card>
      )}

      {step === 1 && (
        <Card>
          <Form layout="vertical">
            <Form.Item label="目标动画风格">
              <Select
                value={style}
                onChange={setStyle}
                options={[
                  { value: '日系动画', label: '🇯🇵 日系动画' },
                  { value: '美式卡通', label: '🇺🇸 美式卡通' },
                  { value: '水彩风', label: '🎨 水彩风' },
                  { value: '写实风格', label: '📸 写实风格' },
                  { value: '国风武侠', label: '🏯 国风武侠' },
                  { value: '赛博朋克', label: '🌃 赛博朋克' },
                ]}
              />
            </Form.Item>
            <Form.Item label="额外提示（可选）" extra="告诉 LLM 你想重点关注的方面，比如：'重点突出主角心理活动'，'注意服装细节'">
              <Input.TextArea
                value={extraHint}
                onChange={(e) => setExtraHint(e.target.value)}
                rows={3}
                placeholder="（可选）"
              />
            </Form.Item>
            <Space>
              <Button onClick={() => setStep(0)}>上一步</Button>
              <Button type="primary" icon={<FileSearchOutlined />} onClick={onAnalyze}>
                开始剖析
              </Button>
            </Space>
          </Form>
        </Card>
      )}

      {step >= 2 && job && (
        <Card
          title={
            <Space>
              <span>剖析进度</span>
              <Tag color={job.status === 'success' ? 'success' : job.status === 'failed' ? 'error' : 'processing'}>
                {job.status}
              </Tag>
            </Space>
          }
          extra={done && (
            <Space>
              <Button icon={<DownloadOutlined />} onClick={onExport}>导出 Markdown</Button>
              <Button icon={<DownloadOutlined />} onClick={onExportJson}>导出 JSON</Button>
            </Space>
          )}
        >
          <Progress
            percent={Math.round((job.progress || 0) * 100)}
            status={job.status === 'failed' ? 'exception' : job.status === 'success' ? 'success' : 'active'}
          />
          <Paragraph style={{ marginTop: 12 }}>
            <b>当前阶段：</b>{job.stage || '准备中'}&emsp;
            <b>消息：</b>{job.message || '-'}
          </Paragraph>
          {job.status === 'failed' && <Alert type="error" message={job.message || '剖析失败'} />}
          {done && <AnalysisResult report={report} />}
        </Card>
      )}
    </div>
  )
}

// --------- 报告渲染组件 ---------
function AnalysisResult({ report }: { report: Report }) {
  if (!report || Object.keys(report).length === 0) {
    return <Alert type="info" message="报告为空" />
  }

  return (
    <div style={{ marginTop: 16 }}>
      {report._fallback && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="LLM 深度剖析未成功，当前为简化兜底版本"
          description="请检查「🔧 模型配置 → 🧠 LLM」API Key，并建议使用非 reasoning 模型（如 deepseek-chat-v3 / gpt-4o-mini / qwen3-30b-instruct）"
        />
      )}
      <Tabs
        defaultActiveKey="overview"
        items={[
          { key: 'overview', label: '📖 概要', children: <OverviewTab report={report} /> },
          { key: 'characters', label: `👥 角色 (${report.characters?.length || 0})`, children: <CharactersTab chars={report.characters || []} /> },
          { key: 'script', label: `🎭 剧本 (${report.script?.acts?.length || 0})`, children: <ScriptTab acts={report.script?.acts || []} /> },
          { key: 'storyboard', label: `🎬 分镜 (${report.storyboard?.length || 0})`, children: <StoryboardTab shots={report.storyboard || []} /> },
          { key: 'raw', label: '🧾 原始 JSON', children: <pre style={{ maxHeight: 500, overflow: 'auto', background: '#1a1a1a', color: '#ddd', padding: 12, borderRadius: 4 }}>{JSON.stringify(report, null, 2)}</pre> },
        ]}
      />
    </div>
  )
}

function OverviewTab({ report }: { report: Report }) {
  return (
    <Descriptions column={1} bordered size="small">
      <Descriptions.Item label="标题">{report.title || '-'}</Descriptions.Item>
      <Descriptions.Item label="类型">{report.genre ? <Tag color="purple">{report.genre}</Tag> : '-'}</Descriptions.Item>
      <Descriptions.Item label="一句话概要">{report.summary || '-'}</Descriptions.Item>
      <Descriptions.Item label="整体氛围">{report.tone || '-'}</Descriptions.Item>
      <Descriptions.Item label="BGM 建议">{report.bgm_hint || '-'}</Descriptions.Item>
      <Descriptions.Item label="制作备注">{report.notes || '-'}</Descriptions.Item>
      <Descriptions.Item label="统计">
        页数 {report._meta?.page_count ?? '?'}&emsp;
        分格 {report._meta?.panel_count ?? '?'}&emsp;
        角色聚类 {report._meta?.character_cluster_count ?? '?'}
      </Descriptions.Item>
    </Descriptions>
  )
}

function CharactersTab({ chars }: { chars: Character[] }) {
  if (!chars.length) return <Alert type="info" message="LLM 未识别出角色" />
  return (
    <Row gutter={[16, 16]}>
      {chars.map((c, i) => (
        <Col xs={24} md={12} key={i}>
          <Card
            size="small"
            title={<Space>
              <Text strong>{c.name}</Text>
              {c.role && <Tag color={c.role.includes('主') ? 'red' : 'blue'}>{c.role}</Tag>}
            </Space>}
          >
            <Descriptions column={1} size="small">
              {c.appearance && <Descriptions.Item label="外貌">{c.appearance}</Descriptions.Item>}
              {c.costume && <Descriptions.Item label="服装">{c.costume}</Descriptions.Item>}
              {c.personality && <Descriptions.Item label="性格">{c.personality}</Descriptions.Item>}
              {c.voice_tone && <Descriptions.Item label="声线">{c.voice_tone}</Descriptions.Item>}
              {c.first_appear_panel != null && <Descriptions.Item label="首次出场">第 {c.first_appear_panel} 格</Descriptions.Item>}
            </Descriptions>
          </Card>
        </Col>
      ))}
    </Row>
  )
}

function ScriptTab({ acts }: { acts: Act[] }) {
  if (!acts.length) return <Alert type="info" message="LLM 未产出剧本结构" />
  return (
    <Table
      size="small"
      rowKey={(_, i) => i!.toString()}
      pagination={false}
      dataSource={acts}
      columns={[
        { title: '段落', dataIndex: 'name', width: 160, render: (v) => <Tag color="geekblue">{v}</Tag> },
        { title: '分格范围', dataIndex: 'panels_range', width: 120, render: (v) => v ? `${v[0]} - ${v[1]}` : '-' },
        { title: '剧情概要', dataIndex: 'summary' },
      ]}
    />
  )
}

function StoryboardTab({ shots }: { shots: Shot[] }) {
  if (!shots.length) return <Alert type="info" message="没有分镜数据" />
  return (
    <div>
      {shots.map((s) => (
        <Card
          key={s.index}
          size="small"
          style={{ marginBottom: 12 }}
          title={
            <Space wrap>
              <Tag color="gold">#{s.index}</Tag>
              {s.timecode && <Tag>{s.timecode}</Tag>}
              {s.shot_type && <Tag color="purple">{s.shot_type}</Tag>}
              {s.camera_motion && <Tag color="cyan">{s.camera_motion}</Tag>}
              {s.environment?.time_of_day && <Tag color="blue">{s.environment.time_of_day}</Tag>}
            </Space>
          }
        >
          <Row gutter={12}>
            {s.panel_image_url && (
              <Col xs={24} md={6}>
                <img
                  src={s.panel_image_url}
                  alt={`panel-${s.index}`}
                  style={{ width: '100%', borderRadius: 4, background: '#000' }}
                />
              </Col>
            )}
            <Col xs={24} md={s.panel_image_url ? 18 : 24}>
              <Descriptions column={2} size="small" bordered>
                {s.environment?.location && <Descriptions.Item label="地点">{s.environment.location}</Descriptions.Item>}
                {s.environment?.weather && <Descriptions.Item label="天气">{s.environment.weather}</Descriptions.Item>}
                {s.environment?.lighting && <Descriptions.Item label="光影">{s.environment.lighting}</Descriptions.Item>}
                {s.environment?.details && <Descriptions.Item label="环境细节" span={2}>{s.environment.details}</Descriptions.Item>}
                {s.dialogue && (
                  <Descriptions.Item label={`台词${s.speaker ? `（${s.speaker}）` : ''}`} span={2}>
                    💬 {s.dialogue}
                  </Descriptions.Item>
                )}
                {s.sfx && <Descriptions.Item label="音效" span={2}>🔊 {s.sfx}</Descriptions.Item>}
              </Descriptions>

              {(s.characters_in_shot?.length || 0) > 0 && (
                <div style={{ marginTop: 8 }}>
                  <Text strong>镜头内角色：</Text>
                  {s.characters_in_shot!.map((ch, i) => (
                    <Card key={i} size="small" style={{ marginTop: 4 }}>
                      <Space wrap>
                        <Tag color="red">{ch.name}</Tag>
                        {ch.emotion && <Tag color="volcano">情绪:{ch.emotion}</Tag>}
                      </Space>
                      <div style={{ fontSize: 12, color: '#aaa', marginTop: 4 }}>
                        {ch.costume && <div>👗 服装：{ch.costume}</div>}
                        {ch.action && <div>🎬 动作：{ch.action}</div>}
                        {ch.expression && <div>😊 神态：{ch.expression}</div>}
                      </div>
                    </Card>
                  ))}
                </div>
              )}

              {s.image_prompt && (
                <div style={{ marginTop: 8 }}>
                  <Text strong>🖼 图像 prompt：</Text>
                  <pre style={{ background: '#1a1a1a', color: '#9ec5fe', padding: 6, borderRadius: 4, fontSize: 12, whiteSpace: 'pre-wrap', margin: 0 }}>{s.image_prompt}</pre>
                </div>
              )}
              {s.video_prompt && (
                <div style={{ marginTop: 4 }}>
                  <Text strong>🎥 视频 prompt：</Text>
                  <pre style={{ background: '#1a1a1a', color: '#b5e4b5', padding: 6, borderRadius: 4, fontSize: 12, whiteSpace: 'pre-wrap', margin: 0 }}>{s.video_prompt}</pre>
                </div>
              )}
            </Col>
          </Row>
        </Card>
      ))}
    </div>
  )
}
