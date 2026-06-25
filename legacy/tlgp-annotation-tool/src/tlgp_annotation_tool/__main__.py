import argparse
import sys

from tlgp_annotation_tool.app import TlgpAnnotationApp


def main():
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")  # noqa: B009
    getattr(sys.stderr, "reconfigure")(encoding="utf-8")  # noqa: B009

    parser = argparse.ArgumentParser(description="TLGP Annotation Tool")
    parser.add_argument(
        "image", nargs="?", default=None, help="Screenshot image path to open"
    )
    parser.add_argument(
        "-s",
        "--session",
        default=None,
        help="Previously exported session JSON to re-edit",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Default output directory for export. When set, export skips the directory picker.",
    )
    args = parser.parse_args()

    app = TlgpAnnotationApp(
        initial_image=args.image,
        session_path=args.session,
        default_output_dir=args.output,
    )
    app.mainloop()


if __name__ == "__main__":
    main()
