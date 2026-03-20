import { Header } from './Header'
import { Sidebar } from './Sidebar'
import styles from './AppLayout.module.css'

export function AppLayout({ children }) {
  return (
    <div className={styles.shell}>
      <Header />
      <div className={styles.body}>
        <Sidebar />
        <main className={styles.main}>
          {children}
        </main>
      </div>
    </div>
  )
}
