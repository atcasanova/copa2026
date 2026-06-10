import React, { useEffect, useState } from 'react'
import { Link as RouterLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  Alert,
  AppBar, Box, Drawer, IconButton, List, ListItem, ListItemButton,
  ListItemIcon, ListItemText, Toolbar, Typography, Avatar, Divider, Badge, Link as MuiLink, useMediaQuery, useTheme
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
import axios from 'axios'
import { useAuth } from '../App'

const drawerWidth = 260;

export default function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('md'))
  const [mobileOpen, setMobileOpen] = useState(false)
  const [groupNotificationsCount, setGroupNotificationsCount] = useState(0)
  const [adminNotificationsCount, setAdminNotificationsCount] = useState(0)
  const [whatsappGroupChat, setWhatsappGroupChat] = useState('')

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen)
  }

  const loadNavigationNotifications = async () => {
    if (!user) {
      setGroupNotificationsCount(0)
      setAdminNotificationsCount(0)
      return
    }

    try {
      const groupRes = await axios.get('/api/groups/invitations/pending')
      setGroupNotificationsCount(groupRes.data.length || 0)
    } catch (err) {
      setGroupNotificationsCount(0)
    }

    if (user.role === 'system_admin' || user.role === 'score_admin') {
      try {
        const adminRes = await axios.get('/api/admin/notifications/summary')
        setAdminNotificationsCount(adminRes.data.total || 0)
      } catch (err) {
        setAdminNotificationsCount(0)
      }
    } else {
      setAdminNotificationsCount(0)
    }
  }

  useEffect(() => {
    loadNavigationNotifications()
    const interval = window.setInterval(loadNavigationNotifications, 60000)

    const handleFocus = () => loadNavigationNotifications()
    window.addEventListener('focus', handleFocus)

    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', handleFocus)
    }
  }, [user?.id, user?.role, location.pathname])

  useEffect(() => {
    if (!user) {
      setWhatsappGroupChat('')
      return
    }

    axios.get('/api/auth/profile-config')
      .then(res => setWhatsappGroupChat(res.data?.whatsapp_group_chat || ''))
      .catch(() => setWhatsappGroupChat(''))
  }, [user?.id])

  const menuItems = [
    { text: 'Painel Geral', icon: <DashIcon />, path: '/' },
    { text: 'Meus Palpites', icon: <SoccerIcon />, path: '/predictions' },
    { text: 'Classificação', icon: <RankIcon />, path: '/rankings' },
    { text: 'Tabela', icon: <TableIcon />, path: '/tables' },
    { text: 'Grupos', icon: <GroupsIcon />, path: '/groups', badgeCount: groupNotificationsCount },
    { text: 'Meu Perfil', icon: <ProfileIcon />, path: '/profile' },
    { text: 'Auditoria', icon: <AuditIcon />, path: '/audit' },
    { text: 'Regras do Bolão', icon: <HelpIcon />, path: '/rules' },
  ]

  // Add Admin Console option if user is system_admin or score_admin
  if (user && (user.role === 'system_admin' || user.role === 'score_admin')) {
    menuItems.push({ text: 'Administração', icon: <AdminIcon />, path: '/admin', badgeCount: adminNotificationsCount })
  }

  const shouldShowPaymentNotice = user &&
    !['system_admin', 'score_admin'].includes(user.role) &&
    user.payment_status !== 'approved'

  const drawerContent = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', bgcolor: 'background.paper' }}>
      <Toolbar sx={{ justifyContent: 'center', py: 2 }}>
        <Typography variant="h5" sx={{ fontWeight: 800, color: 'primary.main', display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box component="img" src="/icons/icon-192.png" alt="Logo" sx={{ width: 28, height: 28 }} />
          Bolão 2026
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
                  <Badge badgeContent={item.badgeCount || 0} color="warning" invisible={!item.badgeCount} max={99}>
                    {item.icon}
                  </Badge>
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
        {shouldShowPaymentNotice && (
          <Alert
            severity="warning"
            sx={{
              position: 'sticky',
              top: { xs: 80, sm: 88 },
              zIndex: theme.zIndex.appBar - 1,
              mb: 3,
              borderRadius: 2,
              fontWeight: 600,
              '& .MuiAlert-message': { width: '100%' }
            }}
          >
            Você só poderá dar palpites após ter seu pagamento aprovado pelo admin. Faça o pagamento na seção{' '}
            <MuiLink component={RouterLink} to="/profile" color="inherit" sx={{ fontWeight: 800, textDecoration: 'underline' }}>
              Meu Perfil
            </MuiLink>
            {whatsappGroupChat && (
              <>
                {' '}ou no{' '}
                <MuiLink href={whatsappGroupChat} target="_blank" rel="noopener noreferrer" color="inherit" sx={{ fontWeight: 800, textDecoration: 'underline' }}>
                  grupo de chat do bolão
                </MuiLink>
              </>
            )}
            .
          </Alert>
        )}
        <Outlet />
      </Box>
    </Box>
  )
}
