import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { InternalCashBoxListController } from "./internal_cash_box_list_controller";

export const internalCashBoxListView = {
    ...listView,
    Controller: InternalCashBoxListController,
};

registry.category("views").add("internal_cash_box_list", internalCashBoxListView);
