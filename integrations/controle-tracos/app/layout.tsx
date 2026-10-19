import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata={metadataBase:new URL("http://localhost:3000"),title:"Controle de Traços | Motiva",description:"Recebimento, análise e organização de cartas traço.",openGraph:{title:"Controle de Traços | Motiva",description:"Recebimento, análise e organização técnica.",images:["/og.png"]},twitter:{card:"summary_large_image",title:"Controle de Traços | Motiva",description:"Recebimento, análise e organização técnica.",images:["/og.png"]}};
export default function RootLayout({children}:Readonly<{children:React.ReactNode}>){return <html lang="pt-BR"><body>{children}</body></html>}
