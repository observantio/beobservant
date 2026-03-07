import PropTypes from "prop-types";
import { Select } from "../../components/ui";

export default function DatasourceSelector({
  datasourceUid,
  onDatasourceChange,
  datasources,
  label = "Default Datasource",
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-sre-text mb-2">
        {label}
      </label>
      <Select
        value={datasourceUid}
        onChange={(e) => onDatasourceChange(e.target.value)}
        required
      >
        <option value="" disabled>
          Select a datasource
        </option>
        {datasources.map((ds) => (
          <option key={ds.uid} value={ds.uid}>
            {ds.name} ({ds.type})
          </option>
        ))}
      </Select>
    </div>
  );
}

DatasourceSelector.propTypes = {
  datasourceUid: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  onDatasourceChange: PropTypes.func.isRequired,
  datasources: PropTypes.array,
  label: PropTypes.string,
};
