import { PageHeader } from "../components/PageHeader";
import { Scorecard } from "../components/Scorecard";
import { useShell } from "../ShellContext";

export function Offices() {
  const { scores } = useShell();
  return (
    <>
      <PageHeader title="Offices">Which office is keeping its promises? Counted by the server from the complaints, not by the AI.</PageHeader>
      <div className="page-body">
        <Scorecard rows={scores} />
      </div>
    </>
  );
}
