import React, { useEffect, useState } from 'react'
import {
  Alert, Box, Card, CardContent, Chip, Grid, Paper, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, Typography
} from '@mui/material'
import axios from 'axios'
import GroupStandingsTable from '../components/GroupStandingsTable'
import { buildGroupStandings } from '../utils/standings'

const formatGroupName = (groupName) => {
  if (!groupName) return ''
  return groupName.toLowerCase().startsWith('group ') ? groupName.replace(/^group\s+/i, '') : groupName
}

export default function Tables() {
  const [groups, setGroups] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true)
        const res = await axios.get('/api/matches')
        setGroups(buildGroupStandings(res.data))
      } catch (err) {
        setError('Erro ao carregar tabelas dos grupos.')
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  const renderScore = (match) => {
    if (match.score_ft_team1 === null || match.score_ft_team1 === undefined || match.score_ft_team2 === null || match.score_ft_team2 === undefined) {
      return <Chip label="A definir" size="small" variant="outlined" />
    }
    return (
      <Chip
        label={`${match.score_ft_team1} x ${match.score_ft_team2}`}
        color="primary"
        size="small"
        variant="outlined"
        sx={{ fontWeight: 800, fontFamily: 'Outfit' }}
      />
    )
  }

  const formatDateTime = (isoString) => {
    const d = new Date(isoString)
    return d.toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'America/Sao_Paulo'
    })
  }

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="h4" gutterBottom sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 3 }}>
        Tabela da Copa
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>{error}</Alert>}

      {loading ? (
        <Alert severity="info" sx={{ borderRadius: 2 }}>Carregando tabelas...</Alert>
      ) : groups.length === 0 ? (
        <Alert severity="info" sx={{ borderRadius: 2 }}>Nenhum grupo encontrado.</Alert>
      ) : (
        <Grid container spacing={3}>
          {groups.map(group => (
            <Grid item xs={12} lg={6} key={group.groupName}>
              <Card>
                <CardContent sx={{ p: { xs: 2, sm: 3 } }}>
                  <Typography variant="h6" sx={{ fontWeight: 800, fontFamily: 'Outfit', mb: 2 }}>
                    Grupo {formatGroupName(group.groupName)}
                  </Typography>

                  <Stack spacing={2}>
                    <GroupStandingsTable standings={group.standings} dense />

                    <TableContainer component={Paper} sx={{ boxShadow: 'none', borderRadius: 2 }}>
                      <Table size="small">
                        <TableHead>
                          <TableRow>
                            <TableCell>Jogo</TableCell>
                            <TableCell align="center">Resultado</TableCell>
                            <TableCell align="right">Data</TableCell>
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {group.matches.map(match => (
                            <TableRow key={match.id}>
                              <TableCell>
                                <Typography variant="body2" sx={{ fontWeight: 700 }}>
                                  {match.team1_name} x {match.team2_name}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {match.ground}
                                </Typography>
                              </TableCell>
                              <TableCell align="center">{renderScore(match)}</TableCell>
                              <TableCell align="right">
                                <Typography variant="caption" color="text.secondary">
                                  {formatDateTime(match.kickoff_time)}
                                </Typography>
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  )
}
