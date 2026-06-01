import React, { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  AppBar, Box, Drawer, IconButton, List, ListItem, ListItemButton,
  ListItemIcon, ListItemText, Toolbar, Typography, Button, Avatar, Divider, useMediaQuery, useTheme
} from '@mui/material'
import {
  Menu as MenuIcon,
  Dashboard as DashIcon,
  SportsSoccer as SoccerIcon,
  FormatListNumbered as RankIcon,
  TableChart as TableIcon,
  Groups as GroupsIcon,
  Person as ProfileIcon,
  AdminPanelSettings as AdminIcon,
  ExitToApp as LogoutIcon,
  HelpOutline as HelpIcon,
  VerifiedUser as AuditIcon
} from '@mui/icons-material'
import { useAuth } from '../App'

const drawerWidth = 260;

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen)
  }

  const menuItems = [
    { text: 'Painel Geral', icon: <DashIcon />, path: '/' },
    { text: 'Meus Palpites', icon: <SoccerIcon />, path: '/predictions' },
    { text: 'Classificação', icon: <RankIcon />, path: '/rankings' },
    { text: 'Tabela', icon: <TableIcon />, path: '/tables' },
    { text: 'Grupos', icon: <GroupsIcon />, path: '/groups' },
    { text: 'Meu Perfil', icon: <ProfileIcon />, path: '/profile' },
    { text: 'Auditoria', icon: <AuditIcon />, path: '/audit' },
    { text: 'Regras do Bolão', icon: <HelpIcon />, path: '/rules' },
  ]

  // Add Admin Console option if user is system_admin or score_admin
  if (user && (user.role === 'system_admin' || user.role === 'score_admin')) {
    menuItems.push({ text: 'Administração', icon: <AdminIcon />, path: '/admin' })
  }

  const drawerContent = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', bgcolor: 'background.paper' }}>
      <Toolbar sx={{ justifyContent: 'center', py: 2 }}>
        <Typography variant="h5" sx={{ fontWeight: 800, color: 'primary.main', display: 'flex', alignItems: 'center', gap: 1 }}>
          ⚽ Bolão 2026
        </Typography>
      </Toolbar>
      <Divider />
      
      {/* User Quick Info */}
      <Box sx={{ p: 3, display: 'flex', alignItems: 'center', gap: 2 }}>
        <Avatar 
          src={user?.avatar_url || ''} 
          alt={user?.display_name}
          sx={{ width: 48, height: 48, bgcolor: 'secondary.main', color: 'secondary.contrastText', fontWeight: 'bold' }}
        >
          {user?.display_name?.charAt(0).toUpperCase()}
        </Avatar>
        <Box sx={{ overflow: 'hidden' }}>
          <Typography variant="subtitle2" noWrap sx={{ fontWeight: 600 }}>
            {user?.display_name}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
            {user?.role === 'system_admin' ? 'Admin Geral' :
             user?.role === 'score_admin' ? 'Admin Resultados' :
             user?.role === 'group_admin' ? 'Admin de Grupo' : 'Participante'}
          </Typography>
        </Box>
      </Box>
      <Divider />

      <List sx={{ px: 2, py: 1, flexGrow: 1 }}>
        {menuItems.map((item) => {
          const active = location.pathname === item.path || (item.path !== '/' && location.pathname.startsWith(item.path));
          return (
            <ListItem key={item.text} disablePadding sx={{ mb: 0.5 }}>
              <ListItemButton
                onClick={() => {
                  navigate(item.path)
                  if (isMobile) setMobileOpen(false)
                }}
                sx={{
                  borderRadius: 2,
                  bgcolor: active ? 'rgba(16, 185, 129, 0.1)' : 'transparent',
                  color: active ? 'primary.main' : 'text.primary',
                  '&:hover': {
                    bgcolor: active ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255, 255, 255, 0.05)',
                  },
                }}
              >
                <ListItemIcon sx={{ color: active ? 'primary.main' : 'text.secondary', minWidth: 40 }}>
                  {item.icon}
                </ListItemIcon>
                <ListItemText primary={item.text} primaryTypographyProps={{ fontWeight: active ? 600 : 500, fontSize: '0.95rem' }} />
              </ListItemButton>
            </ListItem>
          )
        })}
      </List>
      
      <Divider />
      <List sx={{ p: 2 }}>
        <ListItem disablePadding>
          <ListItemButton
            onClick={logout}
            sx={{
              borderRadius: 2,
              color: 'error.main',
              '&:hover': { bgcolor: 'rgba(239, 68, 68, 0.1)' }
            }}
          >
            <ListItemIcon sx={{ color: 'error.main', minWidth: 40 }}>
              <LogoutIcon />
            </ListItemIcon>
            <ListItemText primary="Sair da Conta" primaryTypographyProps={{ fontWeight: 600 }} />
          </ListItemButton>
        </ListItem>
      </List>
    </Box>
  )

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar
        position="fixed"
        sx={{
          width: { md: `calc(100% - ${drawerWidth}px)` },
          ml: { md: `${drawerWidth}px` },
          bgcolor: 'rgba(11, 15, 25, 0.8)',
          backdropFilter: 'blur(12px)',
          borderBottom: '1px solid #1f2937',
          boxShadow: 'none',
        }}
      >
        <Toolbar sx={{ justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center' }}>
            <IconButton
              color="inherit"
              aria-label="open drawer"
              edge="start"
              onClick={handleDrawerToggle}
              sx={{ mr: 2, display: { md: 'none' } }}
            >
              <MenuIcon />
            </IconButton>
            <Typography variant="h6" noWrap component="div" sx={{ fontWeight: 700, fontFamily: 'Outfit' }}>
              {location.pathname === '/' ? 'Painel do Participante' :
               location.pathname.startsWith('/predictions') ? 'Meus Palpites' :
               location.pathname.startsWith('/rankings') ? 'Classificação e Ligas' :
               location.pathname.startsWith('/tables') ? 'Tabela da Copa' :
               location.pathname.startsWith('/groups') ? 'Grupos de Amigos' :
               location.pathname.startsWith('/profile') ? 'Configurações de Perfil' :
               location.pathname.startsWith('/rules') ? 'Regras e Funcionamento' :
               location.pathname.startsWith('/audit') ? 'Auditoria Criptográfica' :
               location.pathname.startsWith('/admin') ? 'Painel de Controle' : 'Bolão'}
            </Typography>
          </Box>
          
          {/* Default Timezone Indicator */}
          <Typography variant="caption" sx={{ color: 'text.secondary', display: { xs: 'none', sm: 'block' } }}>
            Fuso Horário: <strong>America/Sao_Paulo (UTC-3)</strong>
          </Typography>
        </Toolbar>
      </AppBar>

      <Box
        component="nav"
        sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}
        aria-label="mailbox folders"
      >
        {/* Mobile Drawer */}
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth, borderRight: '1px solid #1f2937' },
          }}
        >
          {drawerContent}
        </Drawer>
        
        {/* Desktop Drawer */}
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            '& .MuiDrawer-paper': { boxSizing: 'border-box', width: drawerWidth, borderRight: '1px solid #1f2937' },
          }}
          open
        >
          {drawerContent}
        </Drawer>
      </Box>

      {/* Main Content Area */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: { xs: 2, sm: 3 },
          width: { md: `calc(100% - ${drawerWidth}px)` },
          minWidth: 0, // Prevents flex children from stretching the layout on mobile
          mt: '64px', // Space for Toolbar
          color: 'text.primary',
        }}
      >
        <Outlet />
      </Box>
    </Box>
  )
}
