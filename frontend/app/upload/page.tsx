import { redirect } from "next/navigation";

// Uploading now lives behind the admin login.
export default function UploadRedirect() {
  redirect("/admin");
}
