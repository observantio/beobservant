import PropTypes from "prop-types";
import { Card, Badge, Button } from "../ui";

export default function GroupCard({
  group,
  usersCount,
  permsCount,
  onOpenPermissions,
  onEdit,
  onDelete,
}) {
  return (
    <Card className="p-0 relative overflow-visible bg-gradient-to-br from-sre-surface to-sre-surface/80 border border-sre-border hover:border-sre-primary/30 hover:shadow-lg transition-all duration-200 backdrop-blur-sm rounded-lg group">
      <div className="p-4">
        <div className="flex items-start gap-3 mb-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-sre-primary/20 to-sre-primary/10 text-sre-primary flex items-center justify-center font-semibold border border-sre-border/50 flex-shrink-0">
            <span className="material-icons text-xl">groups</span>
          </div>
          <div className="flex-1 min-w-0">
            <h3
              className="text-lg font-bold text-sre-text truncate"
              title={group.name}
            >
              {group.name}
            </h3>
            <p
              className="text-xs text-sre-text-muted truncate"
              title={group.description || "No description"}
            >
              {group.description || "No fun when there's no description"}
            </p>
          </div>
        </div>

        <div className="mb-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge
              variant="info"
              className="whitespace-nowrap text-xs px-2.5 py-0.5 font-medium"
            >
              <span className="material-icons text-xs mr-1">security</span>
              {permsCount} permission{permsCount !== 1 ? "s" : ""}
            </Badge>
            <Badge
              variant="success"
              className="whitespace-nowrap text-xs px-2.5 py-0.5 font-medium"
            >
              <span className="material-icons text-xs mr-1">person</span>
              {usersCount} member{usersCount !== 1 ? "s" : ""}
            </Badge>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 items-center pt-2 border-t border-sre-border/30">
          <Button
            size="sm"
            variant="ghost"
            className="h-8 px-2.5 text-xs flex items-center gap-1.5 hover:bg-sre-primary/10 hover:text-sre-primary transition-colors"
            onClick={() => onOpenPermissions(group)}
            aria-label={`Permissions for ${group.name}`}
          >
            <span className="material-icons text-sm">security</span>
            <span>Permissions</span>
          </Button>

          <Button
            size="sm"
            variant="ghost"
            className="h-8 px-2.5 text-xs flex items-center gap-1.5 hover:bg-sre-primary/10 hover:text-sre-primary transition-colors"
            onClick={() => onEdit(group)}
            aria-label={`Edit ${group.name}`}
          >
            <span className="material-icons text-sm">edit</span>
            <span>Edit</span>
          </Button>

          <Button
            size="sm"
            variant="ghost"
            className="h-8 px-2.5 text-xs flex items-center gap-1.5 hover:bg-red-500/10 hover:text-red-500 transition-colors"
            onClick={() => onDelete(group)}
            aria-label={`Delete ${group.name}`}
          >
            <span className="material-icons text-sm">delete</span>
            <span>Delete</span>
          </Button>
        </div>
      </div>
    </Card>
  );
}

GroupCard.propTypes = {
  group: PropTypes.object.isRequired,
  usersCount: PropTypes.number.isRequired,
  permsCount: PropTypes.number.isRequired,
  onOpenPermissions: PropTypes.func.isRequired,
  onEdit: PropTypes.func.isRequired,
  onDelete: PropTypes.func.isRequired,
};
