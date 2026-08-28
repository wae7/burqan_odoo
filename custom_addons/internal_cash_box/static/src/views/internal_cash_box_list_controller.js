import { useService } from "@web/core/utils/hooks";
import { ListController } from "@web/views/list/list_controller";

export class InternalCashBoxListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
    }

    async onClickPost() {
        const selection = this.model.root.selection;
        let resIds;
        if (selection.length) {
            resIds = selection.map((record) => record.resId);
        } else {
            const domain = this.model.root.domain || [];
            resIds = await this.orm.search("internal.cash.box", domain);
        }
        const result = await this.orm.call("internal.cash.box", "action_post", [resIds], {});
        if (result?.tag === "display_notification") {
            this.notification.add(result.params.message, {
                title: result.params.title,
                type: result.params.type,
            });
        }
        await this.model.load();
    }
}

InternalCashBoxListController.template = "internal_cash_box.ListView";
