import sys
import fit.utils as fit_utils
import json
parsed_info = fit_utils.parse_fit_file(sys.argv[1], None, "")
print(json.dumps(parsed_info, indent=4, default=str))