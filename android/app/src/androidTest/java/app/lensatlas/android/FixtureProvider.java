package app.lensatlas.android;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.graphics.Bitmap;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

/** Synthetic data in the test APK's private directory; no phone albums involved. */
public class FixtureProvider extends ContentProvider {
    private File image;
    @Override public boolean onCreate() {
        image = new File(getContext().getFilesDir(), "synthetic-fixture.jpg");
        Bitmap bitmap = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888);
        bitmap.eraseColor(android.graphics.Color.GREEN);
        try {
            try (FileOutputStream out = new FileOutputStream(image)) { bitmap.compress(Bitmap.CompressFormat.JPEG, 90, out); }
            ExifInterface exif = new ExifInterface(image);
            exif.setAttribute(ExifInterface.TAG_MAKE, "SYNTHETIC");
            exif.setAttribute(ExifInterface.TAG_MODEL, "Fixture Camera");
            exif.setAttribute(ExifInterface.TAG_DATETIME_ORIGINAL, "2026:10:05 12:00:00");
            exif.setAttribute(ExifInterface.TAG_FOCAL_LENGTH, "24/1");
            exif.saveAttributes();
        } catch (IOException e) { throw new IllegalStateException(e); }
        finally { bitmap.recycle(); }
        return true;
    }
    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String sort) {
        String[] columns = projection == null ? new String[] {"_id"} : projection;
        MatrixCursor cursor = new MatrixCursor(columns);
        for (long id = 1; id <= 2; id++) {
            Map<String, Object> values = new HashMap<>();
            values.put("_id", id); values.put("_display_name", "SYNTHETIC-" + id + ".jpg");
            values.put("bucket_id", Long.toString(id)); values.put("bucket_display_name", "Fixture-" + id);
            values.put("relative_path", "Fixture-" + id + "/"); values.put("_size", image.length());
            values.put("date_modified", 1L); values.put("width", 8); values.put("height", 8); values.put("datetaken", 0L);
            Object[] row = new Object[columns.length];
            for (int i = 0; i < columns.length; i++) row[i] = values.get(columns[i]);
            cursor.addRow(row);
        }
        return cursor;
    }
    @Override public ParcelFileDescriptor openFile(Uri uri, String mode) throws java.io.FileNotFoundException {
        if (!"r".equals(mode)) throw new SecurityException("Source write prohibited");
        return ParcelFileDescriptor.open(image, ParcelFileDescriptor.MODE_READ_ONLY);
    }
    @Override public String getType(Uri uri) { return "image/jpeg"; }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new SecurityException("Source insert prohibited"); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new SecurityException("Source delete prohibited"); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new SecurityException("Source update prohibited"); }
}
