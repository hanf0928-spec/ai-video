
import { useEffect, useState } from 'react'
import { Button, Card, Form, Input, Modal, Space, Tag, Typography, message } from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { listProjects, createProject, deleteProject } from '../api'
import type { Project } from '../types'

const { Title, Paragraph, Text } = Typography

export default function ProjectsPage() {
  const [list, setList] = useState<Project[]>([])
  const [open, setOpen] = useState(false)
  const [form] = Form.useForm()
  const nav = useNavigate()

  const load = async () => setList(await listProjects())
  useEffect(() => { load() }, [])

  const onCreate = async () => {
    const v = await form.validateFields()
    await createProject(v)
    message.success('项目已创建')
    form.resetFields()
    setOpen(false)
    await load()
  }

  const onDelete = async (id: string) => {
    Modal.confirm({
      title: '删除此项目？',
      okButtonProps: { danger: true },
      onOk: async () => {
        await deleteProject(id)
        message.success('已删除')
        await load()
      },
    })
  }

  return (
    <div>
      <Space style={{ justifyContent: 'space-between', width: '100%', marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0, color: '#fff' }}>我的项目</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          创建项目
        </Button>
      </Space>
      <div className="card-grid">
        {list.map((p) => (
          <div key={p.id} className="project-card" onClick={() => nav(`/projects/${p.id}`)}>
            <Space style={{ justifyContent: 'space-between', width: '100%' }}>
              <Text strong style={{ color: '#fff', fontSize: 16 }}>{p.name}</Text>
              <Button
                size="small" type="text" danger icon={<DeleteOutlined />}
                onClick={(e) => { e.stopPropagation(); onDelete(p.id) }}
              />
            </Space>
            <Paragraph type="secondary" ellipsis={{ rows: 2 }} style={{ marginTop: 8 }}>
              {p.description || '暂无描述'}
            </Paragraph>
            <Space>
              {p.style && <Tag color="purple">{p.style}</Tag>}
              <Tag>{new Date(p.updated_at).toLocaleDateString()}</Tag>
            </Space>
          </div>
        ))}
        {list.length === 0 && (
          <Card style={{ gridColumn: '1 / -1', textAlign: 'center', padding: 48 }}>
            <Text type="secondary">还没有项目，点击右上角「创建项目」开始</Text>
          </Card>
        )}
      </div>

      <Modal title="创建项目" open={open} onOk={onCreate} onCancel={() => setOpen(false)}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="项目名称" rules={[{ required: true }]}>
            <Input placeholder="例：魔法少女小圆" />
          </Form.Item>
          <Form.Item name="description" label="简介">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="style" label="风格">
            <Input placeholder="日系动画 / 水墨 / 像素风 ..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
