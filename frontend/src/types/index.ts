
export interface Project {
  id: string
  name: string
  description?: string
  cover_url?: string
  style?: string
  settings: Record<string, any>
  created_at: string
  updated_at: string
}

export interface Episode {
  id: string
  project_id: string
  index: number
  title: string
  status: string
  script?: string
  video_url?: string
  duration?: number
}

export interface Shot {
  id: string
  episode_id: string
  index: number
  prompt?: string
  dialogue?: string
  speaker?: string
  emotion?: string
  duration: number
  image_url?: string
  video_url?: string
  audio_url?: string
  model_backend: string
  status: string
}

export interface Job {
  id: string
  type: string
  status: 'pending' | 'running' | 'success' | 'failed'
  progress: number
  stage?: string
  message?: string
  result: Record<string, any>
  created_at: string
  updated_at: string
}

export interface MangaUpload {
  id: string
  project_id: string
  filename: string
  file_type: string
  page_count: number
  status: string
}

export interface Character {
  id: string
  project_id: string
  name: string
  description?: string
  reference_images: string[]
  voice_id?: string
  lora_path?: string
}
