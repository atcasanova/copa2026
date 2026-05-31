import React, { useState, useEffect } from 'react'
import { Alert, AlertTitle, Button, Stack, Collapse, Box } from '@mui/material'
import axios from 'axios'

export default function AnnouncementBanner({ onUpdate }) {
  const [announcements, setAnnouncements] = useState([])

  const loadAnnouncements = async () => {
    try {
      const res = await axios.get('/api/announcements')
      // Only display unread announcements
      const unread = res.data.filter(ann => !ann.is_read)
      setAnnouncements(unread)
    } catch (err) {
      console.error('Erro ao buscar comunicados:', err)
    }
  }

  useEffect(() => {
    loadAnnouncements()
  }, [])

  const handleMarkAsRead = async (id) => {
    try {
      await axios.post(`/api/announcements/${id}/read`)
      // Remove from view
      setAnnouncements(prev => prev.filter(ann => ann.id !== id))
      if (onUpdate) onUpdate()
    } catch (err) {
      console.error('Erro ao marcar comunicado como lido:', err)
    }
  }

  if (announcements.length === 0) return null

  return (
    <Stack spacing={2} sx={{ mb: 3 }}>
      {announcements.map((ann) => {
        // Map priority to Alert severity
        const severity = 
          ann.priority === 'high' ? 'error' :
          ann.priority === 'medium' ? 'warning' : 'info';
          
        return (
          <Alert
            key={ann.id}
            severity={severity}
            sx={{
              borderRadius: 3,
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
              '& .MuiAlert-message': { width: '100%' }
            }}
            action={
              <Button 
                color="inherit" 
                size="small" 
                onClick={() => handleMarkAsRead(ann.id)}
                sx={{ fontWeight: 'bold' }}
              >
                Entendido / Lido
              </Button>
            }
          >
            <AlertTitle sx={{ fontWeight: 'bold', fontFamily: 'Outfit' }}>
              {ann.title}
            </AlertTitle>
            {ann.body}
          </Alert>
        )
      })}
    </Stack>
  )
}
