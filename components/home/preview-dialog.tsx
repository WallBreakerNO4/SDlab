import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

type PreviewDialogProps = {
  imageUrl: string | null;
  onOpenChange: (open: boolean) => void;
};

export function PreviewDialog({
  imageUrl,
  onOpenChange,
}: PreviewDialogProps) {
  return (
    <Dialog open={!!imageUrl} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-[90vw] md:max-w-[80vw] lg:max-w-300 w-fit p-0 border-none bg-transparent shadow-none"
        showCloseButton={false}
      >
        <DialogTitle className="sr-only">查看大图</DialogTitle>
        {imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imageUrl}
            alt="Preview"
            className="max-h-[90vh] w-auto object-contain rounded-md cursor-zoom-out"
            onClick={() => onOpenChange(false)}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
