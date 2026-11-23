import { useMemo } from "react";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { buildCommands, groupCommands } from "@/lib/commands";
import { prefetchPath } from "@/lib/routes";

// "Aller à…": every screen and the former top-bar actions, reachable by keyboard from any page, folded sidebar included.
export default function CommandPalette({ open, onOpenChange, onRun }) {
  const groups = useMemo(() => groupCommands(buildCommands()), []);
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <CommandInput placeholder="Aller à… (écran ou action)" data-testid="palette-input" />
      <CommandList data-testid="palette-list">
        <CommandEmpty>Aucun écran ni action ne correspond.</CommandEmpty>
        {groups.map((group) => (
          <CommandGroup key={group.label} heading={group.label}>
            {group.items.map((item) => (
              <CommandItem
                key={item.id}
                value={`${item.group} ${item.label}`}
                keywords={item.keywords}
                onMouseEnter={item.to ? () => prefetchPath(item.to) : undefined}
                onSelect={() => { onOpenChange(false); onRun(item); }}
                data-testid={`palette-${item.id}`}
              >
                {item.label}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
