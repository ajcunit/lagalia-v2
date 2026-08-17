import { MessagesSquare } from "lucide-react";

import { PageHeader } from "../../components/PageHeader";
import { t } from "../../i18n";
import { ChatView } from "./ChatView";

/** Xat general sobre la contractació de l'ens (specs/chat.md). */
export function ChatPage() {
  return (
    <div>
      <PageHeader icon={MessagesSquare} title={t("chat.title")} subtitle={t("chat.intro")} />
      <div className="mt-4">
        <ChatView scope="general" />
      </div>
    </div>
  );
}
