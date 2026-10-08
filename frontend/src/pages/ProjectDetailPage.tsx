
import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Button, Card, Space, Table, Tabs, Tag, Typography, message, Modal, Form, Input,
} from 'antd'
import { PlusOutlined, PlayCircleOutlined } from '@ant-design/icons'
import {
  getProject, listEpisodes, createEpisode, generateEpisode,
} from '../api'
import type { Episode, Project } from '../types'

const { Title, Text } = Typography

export default function ProjectDetailPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [episodes, setEpisodes] = useState<Episode[]>([])
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()

  const load = async () => {
    if (!id) return
    setProject(await getProject(id))
    setEpisodes(await listEpisodes(id))
  }
  useEffect(() => { load() }, [id])

  const onCreateEpisode = async () => {
    const v = await form.validateFields()
    await createEpisode({ project_id: id, index: episodes.length + 1, title: v.title })
    message.success('已创建')
    setOpen(false)
    form.resetFields()
    await load()
  }

  const onRender = async (ep: Episode) => {
    const job = await generateEpisode({ episode_id: ep.id, backend: 'hailuo' })
    message.success(`已提交渲染任务 ${job.id}`)
    nav('/jobs')
  }

  if (!project) return null

  return (
    <div>
      <Title level={3} style={{ color: '#fff' }}>{project.name}</Title>
      <Text type="secondary">{project.description}</Text>

      <Tabs
        style={{ marginTop: 16 }}
        items={[
          {
            key: 'ep', label: '剧集',
            children: (
              <>
                <Space style={{ marginBottom: 12 }}>
                  <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
                    新建剧集
                  </Button>
                </Space>
                <Table
                  rowKey="id"
                  dataSource={episodes}
                  columns={[
                    { title: '#', dataIndex: 'index', width: 60 },
                    { title: '标题', dataIndex: 'title' },
                    {
                      title: '状态', dataIndex: 'status',
                      render: (s) => <Tag color={s === 'done' ? 'green' : s === 'generating' ? 'blue' : 'default'}>{s}</Tag>,
                    },
                    { title: '时长', dataIndex: 'duration', render: (d) => (d ? `${d.toFixed(1)}s` : '-') },
                    {
                      title: '操作',
                      render: (_, r) => (
                        <Space>
                          <Button type="link" onClick={() => nav(`/storyboard/${r.id}`)}>分镜</Button>
                          <Button type="link" icon={<PlayCircleOutlined />} onClick={() => onRender(r)}>渲染</Button>
                          {r.video_url && (
                            <a href={`/static/outputs/${r.project_id}/ep_${r.id}/final.mp4`} target="_blank" rel="noreferrer">
                              预览
                            </a>
                          )}
                        </Space>
                      ),
                    },
                  ]}
                />
              </>
            ),
          },
          {
            key: 'info', label: '项目信息',
            children: (
              <Card>
                <p>ID: {project.id}</p>
                <p>风格: {project.style || '-'}</p>
                <p>创建时间: {new Date(project.created_at).toLocaleString()}</p>
              </Card>
            ),
          },
        ]}
      />

      <Modal title="新建剧集" open={open} onOk={onCreateEpisode} onCancel={() => setOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input placeholder="例：第一集 - 相遇" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
