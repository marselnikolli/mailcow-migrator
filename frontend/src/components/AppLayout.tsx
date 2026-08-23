import { useEffect, useState } from 'react'
import { ChevronsUpDown, Globe, LayoutDashboard, LogOut, Mail, Repeat } from 'lucide-react'
import { useNavigate, useLocation } from 'react-router-dom'
import { authApi } from '../api'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from '@/components/ui/sidebar'
import { Separator } from '@/components/ui/separator'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ModeToggle } from '@/components/mode-toggle'

const navItems = [
  { title: 'Dashboard', href: '/', icon: LayoutDashboard },
  { title: 'Domains', href: '/domains', icon: Globe },
  { title: 'Jobs', href: '/jobs', icon: Repeat },
]

const PAGE_TITLES: Record<string, string> = {
  '/': 'Dashboard',
  '/domains': 'Domain Management',
  '/jobs': 'Migration Jobs',
}

function initialsFrom(email: string) {
  const local = email.split('@')[0] || email
  const parts = local.split(/[._-]/).filter(Boolean)
  const chars = parts.length >= 2 ? [parts[0][0], parts[1][0]] : [local[0], local[1]]
  return chars.filter(Boolean).join('').toUpperCase() || '?'
}

function AppSidebar({ email, role }: { email: string; role: string }) {
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('tenant_id')
    localStorage.removeItem('user_id')
    localStorage.removeItem('role')
    navigate('/login')
  }

  return (
    <Sidebar>
      <SidebarHeader>
        <div className="flex items-center gap-2 px-4 py-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Mail className="h-4 w-4" />
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-semibold">mailcow-migrator</span>
            <span className="text-xs text-muted-foreground">Mail Migration</span>
          </div>
        </div>
        <Separator />
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Menu</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const Icon = item.icon
                const active = location.pathname === item.href
                return (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton asChild isActive={active} tooltip={item.title}>
                      <a href={item.href} onClick={(e) => { e.preventDefault(); navigate(item.href) }}>
                        <Icon />
                        <span>{item.title}</span>
                      </a>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                )
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton className="h-auto py-2">
                  <Avatar className="h-7 w-7">
                    <AvatarFallback className="text-[11px] font-medium">
                      {email ? initialsFrom(email) : '?'}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex min-w-0 flex-col text-left">
                    <span className="truncate text-sm font-medium">{email || 'Loading...'}</span>
                    <span className="truncate text-xs capitalize text-muted-foreground">{role}</span>
                  </div>
                  <ChevronsUpDown className="ml-auto h-4 w-4 text-muted-foreground" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" side="top" className="w-56">
                <DropdownMenuLabel className="font-normal">
                  <div className="flex flex-col space-y-0.5">
                    <p className="truncate text-sm font-medium">{email}</p>
                    <p className="text-xs capitalize text-muted-foreground">{role} · Tenant {localStorage.getItem('tenant_id')}</p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout}>
                  <LogOut className="mr-2 h-4 w-4" />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [role, setRole] = useState(localStorage.getItem('role') || '')

  useEffect(() => {
    authApi
      .getCurrentUser()
      .then((res) => {
        setEmail(res.data.email)
        setRole(res.data.role)
      })
      .catch(() => {})
  }, [])

  const title = PAGE_TITLES[location.pathname] ?? 'mailcow-migrator'

  return (
    <SidebarProvider>
      <div className="flex min-h-screen w-full">
        <AppSidebar email={email} role={role} />
        <SidebarInset>
          <header className="flex h-14 items-center gap-2 border-b px-4">
            <SidebarTrigger />
            <Separator orientation="vertical" className="h-4" />
            <span className="text-sm font-medium">{title}</span>
            <div className="ml-auto flex items-center gap-2">
              <ModeToggle />
            </div>
          </header>
          <main className="flex-1 px-4 py-6 md:px-8">{children}</main>
        </SidebarInset>
      </div>
    </SidebarProvider>
  )
}
