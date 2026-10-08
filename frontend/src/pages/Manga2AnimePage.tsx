
import { useEffect, useState } from 'react'
import {
  Alert, Button, Card, Form, Progress, Radio, Select, Space, Steps, Switch,
  Typography, Upload, message,
} from 'antd'
import type { UploadFile } from 'antd/es/upload/interface'
import { InboxOutlined, PlayCircleOutlined } from '@ant-design/icons'
import { listProjects, uploadManga, convertManga, openJobWS } from '../api'
import type { Project, Job } from '../types'

const { Title, Paragraph } = Typography
const { Dragger } = Upload

export default function Manga2AnimePage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [projectId, setProjectId] = useState<string>()
  const [files, setFiles] = useState<UploadFile[]>([])
  const [uploadId, setUploadId] = useState<string>()
  const [backend, setBackend] = useState<'hailuo' | 'seedance'>('hailuo')
  const [enableBgm, setEnableBgm] = useState(true)
  const [enableSubtitle, setEnableSubtitle] = useState(true)
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

  const onConvert = async () => {
    if (!projectId || !uploadId) return
    const j = await convertManga({
      project_id: projectId, upload_id: uploadId,
      video_backend: backend, enable_bgm: enableBgm, enable_subtitle: enableSubtitle,
      shot_duration: 4.0, resolution: '1080P',
    })
    setJob(j)
    setStep(2)
    const ws = openJobWS(j.id, (snap) => {
      setJob((prev) => prev ? { ...prev, ...snap } : prev)
    })
    return () => ws.close()
  }

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Title level={3} style={{ color: '#fff' }}>🎬 漫画自动转漫剧</Title>
      <Paragraph type="secondary">
        上传静态漫画（PDF / 条漫长图 / 多图），系统将自动完成分格 → OCR → 分镜 → 图生视频 → 配音 → 字幕 → BGM → 合成。
      </Paragraph>

      <Steps
        current={step}
        items={[
          { title: '上传漫画' }, { title: '参数配置' }, { title: '生成中' }, { title: '完成' },
        ]}
        style={{ marginBottom: 24 }}
      />

      {step === 0 && (
        <Card>
          <Form layout="vertical">
            <Form.Item label="所属项目" required>
              <Select
                placeholder="选择或创建项目"
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
            <Form.Item label="视频生成模型">
              <Radio.Group value={backend} onChange={(e) => setBackend(e.target.value)}>
                <Radio.Button value="hailuo">🎥 海螺 03 (MiniMax)</Radio.Button>
                <Radio.Button value="seedance">🎬 Seedance 2 (字节)</Radio.Button>
              </Radio.Group>
            </Form.Item>
            <Form.Item label="自动添加 BGM">
              <Switch checked={enableBgm} onChange={setEnableBgm} />
            </Form.Item>
            <Form.Item label="烧录字幕">
              <Switch checked={enableSubtitle} onChange={setEnableSubtitle} />
            </Form.Item>
            <Space>
              <Button onClick={() => setStep(0)}>上一步</Button>
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={onConvert}>
                开始生成
              </Button>
            </Space>
          </Form>
        </Card>
      )}

      {step >= 2 && job && (
        <Card>
          <Progress
            percent={Math.round((job.progress || 0) * 100)}
            status={job.status === 'failed' ? 'exception' : job.status === 'success' ? 'success' : 'active'}
          />
          <Paragraph>
            <b>当前阶段：</b>{job.stage || '准备中'}<br />
            <b>消息：</b>{job.message || '-'}
          </Paragraph>
          {job.status === 'failed' && <Alert type="error" message={job.message || '生成失败'} />}
          {job.status === 'success' && (
            <>
              <Alert type="success" message="生成完成！" />
              {job.result?.video_path && (
                <video
                  src={`/static/outputs/${job.result.video_path.split('/outputs/')[1]}`}
                  controls style={{ width: '100%', marginTop: 12 }}
                />
              )}
            </>
          )}
        </Card>
      )}
    </div>
  )
}
