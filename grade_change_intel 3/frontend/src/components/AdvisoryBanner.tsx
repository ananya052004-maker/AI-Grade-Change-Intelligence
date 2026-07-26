// SEC-06: every UI screen MUST carry a persistent "Advisory only" affordance.
export function AdvisoryBanner() {
  return (
    <div className="advisory-banner">
      <strong>Advisory only</strong> -- operator retains full control. This System never writes to the QCS/MD-MPC control loop (NG-1, NG-5).
    </div>
  );
}
